from patera.admin import AdminInterface
from .database import User, Category, Question, Exam, Attempt, Session


class Admin(AdminInterface):
    """Operational dashboard and shared exam database models."""

    MANAGED_MODELS = [User, Category, Question, Exam, Attempt, Session]
