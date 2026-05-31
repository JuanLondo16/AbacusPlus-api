from app.domain.ports.repositories import ReceiverRepositoryPort


class GetAllReceiversUseCase:
    def __init__(self, receiver_repo: ReceiverRepositoryPort):
        self.receiver_repo = receiver_repo

    def execute(self) -> list:
        return self.receiver_repo.get_all()
