from patera.admin import AdminInterface

from .models import (
    Attempt,
    AttemptQuestion,
    Category,
    Exam,
    ExamQuestion,
    Question,
    User,
)


class Admin(AdminInterface):
    """
    Patera Admin at /admin. Configured by ``Config.ADMIN``; its sign-in and
    sign-out use the application's JWT endpoints. Users with the ADMIN role
    receive every Admin permission (see AccountService.roles_of).
    """

    MANAGED_MODELS = [
        User,
        Category,
        Question,
        Exam,
        ExamQuestion,
        Attempt,
        AttemptQuestion,
    ]
