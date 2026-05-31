import logging

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

from app.domain.exceptions.base import BrowserLoginException

logger = logging.getLogger(__name__)

CLOUDFLARE_TITLES = ["just a moment", "attention required"]


class PlaywrightBrowserClient:
    def __init__(self, representative: str, nit: str, timeout: int = 60000):
        self._representative = representative
        self._nit = nit
        self._timeout = timeout  # ms

    async def company_login(self, login_url: str) -> tuple[dict[str, str], list[str]]:
        steps: list[str] = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 720},
            )
            page = await context.new_page()
            await stealth_async(page)
            try:
                logger.info("Navegando a: %s", login_url)
                await page.goto(login_url, wait_until="networkidle", timeout=self._timeout)
                steps.append(f"Navegación completada — URL: {page.url}")

                await page.click("#legalRepresentative")
                steps.append("Clic en #legalRepresentative completado")
                logger.info("Clic en #legalRepresentative")

                await self._handle_cloudflare(page, steps)

                await page.fill("#UserCode", self._representative)
                steps.append("Campo #UserCode completado")
                logger.info("Campo #UserCode completado")

                await page.fill("#CompanyCode", self._nit)
                steps.append("Campo #CompanyCode completado")
                logger.info("Campo #CompanyCode completado")

                await page.click("[type=submit]")
                steps.append("Clic en botón Entrar completado")
                logger.info("Clic en botón Entrar")

                await page.wait_for_load_state("networkidle", timeout=self._timeout)
                steps.append(f"Carga post-login completada — URL: {page.url}")

                current_url = page.url
                if "Login" in current_url or "login" in current_url:
                    raise BrowserLoginException(
                        "Login fallido: credenciales inválidas o Cloudflare bloqueó el acceso",
                        steps,
                    )

                raw_cookies = await context.cookies()
                cookies = {c["name"]: c["value"] for c in raw_cookies}
                steps.append(f"Cookies capturadas: {len(cookies)} ({', '.join(cookies.keys())})")
                logger.info("Cookies capturadas por browser: %d", len(cookies))
                return cookies, steps
            except BrowserLoginException:
                raise
            except Exception as e:
                raise BrowserLoginException(
                    f"Error inesperado en paso {len(steps) + 1}: {type(e).__name__}: {e}",
                    steps,
                ) from e
            finally:
                await browser.close()

    async def _handle_cloudflare(self, page, steps: list[str]) -> None:
        """Detecta y resuelve Cloudflare challenge (JS automático o widget interactivo con clic)."""
        for attempt in range(15):
            title = (await page.title()).lower()
            cf_by_title = any(cf in title for cf in CLOUDFLARE_TITLES)

            # Detectar iframe de Cloudflare Turnstile / Managed Challenge
            cf_frames = [f for f in page.frames if "challenges.cloudflare.com" in f.url]

            if not cf_by_title and not cf_frames:
                steps.append(f"Sin challenge Cloudflare — título: '{title}'")
                logger.info("Sin challenge Cloudflare — título: %s", title)
                break

            steps.append(
                f"Cloudflare detectado (intento {attempt + 1}/15) — "
                f"título: '{title}', iframes: {len(cf_frames)}"
            )
            logger.info(
                "Cloudflare detectado (intento %d/15) — iframes: %d", attempt + 1, len(cf_frames)
            )

            if cf_frames:
                cf_frame = cf_frames[0]

                # Esperar a que el iframe cargue su contenido completamente
                await page.wait_for_timeout(3000)

                # El checkbox de Cloudflare es un input nativo oculto dentro de un div
                # con ID dinámico — se busca por estructura: div > input[type='checkbox']
                clicked = False
                for selector in [
                    "div input[type='checkbox']",
                    "input[type='checkbox']",
                ]:
                    try:
                        checkbox = cf_frame.locator(selector).first
                        await checkbox.wait_for(timeout=5000, state="attached")
                        await checkbox.click(force=True)
                        steps.append(
                            f"Clic en checkbox Cloudflare completado (selector: '{selector}')"
                        )
                        logger.info("Clic en checkbox Cloudflare completado: %s", selector)
                        clicked = True
                        break
                    except Exception as e:
                        steps.append(f"Selector '{selector}' falló — {type(e).__name__}: {e}")
                        logger.warning("Selector '%s' falló: %s", selector, e)

                if not clicked:
                    steps.append("Esperando auto-resolución Cloudflare")

            await page.wait_for_timeout(3000)
            await page.wait_for_load_state("networkidle", timeout=30000)
