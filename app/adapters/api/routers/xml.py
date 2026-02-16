from fastapi import APIRouter, UploadFile, File, Depends
from app.application.use_cases.process_xml import ProcessXmlUseCase
from app.dependencies import get_process_xml_use_case

router = APIRouter()


@router.post("/readxml", response_model=dict)
async def read_xml(
    file: UploadFile = File(...),
    use_case: ProcessXmlUseCase = Depends(get_process_xml_use_case),
):
    """
    Process a DIAN electronic invoice ZIP or XML file.

    Args:
        file: ZIP or XML file to process
        use_case: Injected use case
    """
    return await use_case.execute(file)
