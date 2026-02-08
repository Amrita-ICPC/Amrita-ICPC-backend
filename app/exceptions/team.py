from fastapi import status
from uuid import UUID
from app.exceptions.base import AppBaseException

class TeamNotFoundError(AppBaseException):
    """Exception raise when team is not found"""
    def __init__(self,team_id:str):
        super().__init__(
                message=f"Team with ID {team_id} not found",
                status_code=status.HTTP_404_NOT_FOUND,)
    
class UserNotFoundError(AppBaseException):
    """Exception raise when user is not found"""
    def __init__(self,user_id:str):
        super().__init__(
                       message=f"User with ID {user_id} not found",
                       status_code=status.HTTP_404_NOT_FOUND,)
        

class UserAlreadyInTeamError(AppBaseException):
    """Exception raised when the particular user is already present in the team"""
    def __init__(self,team_id:str,user_id:str):
        super().__init__(
            message=f"User with ID: {user_id} is already present in the team :{team_id}",
            status_code=status.HTTP_409_CONFLICT
        )

class UserNotInTeamError(AppBaseException):
    """Exception raised when the particular user is not present in the given team id"""
    def __init__(self,team_id:str,user_id:str):
        super().__init__(
            message=f"User with Id:{user_id} doesn't exists in team:{team_id}",
            status_code=status.HTTP_404_NOT_FOUND
        )