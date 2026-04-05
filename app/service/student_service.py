"""
Student Service - Orchestrates student operations.

This is where business logic lives.
It calls:
1. GUARDS to check permissions
2. VALIDATORS to check business rules
3. REPOSITORIES to query database
4. Converts results to response schemas
"""

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logger import logger
from app.core.guards.student import StudentOperationGuard
from app.exceptions.auth import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError
from app.repositories.student import StudentRepository
from app.repositories.contest import ContestRepository
from app.repositories.team import TeamRepository
from app.repositories.dto.student import PublicContestFilterData
from app.schema.student import (
    StudentPublicContestResponse,
    StudentRegisteredContestResponse,
    StudentContestRegistrationResponse,
)
from app.schema.team import TeamCreate
from app.service.team_service import TeamService
from app.validators.student import StudentValidator
from app.validators.team import TeamValidator


class StudentService:
    """
    Service for student operations.
    
    Think of this as the MANAGER that coordinates everything.
    """

    def __init__(
        self,
        student_repo: StudentRepository,
        contest_repo: ContestRepository,
        team_repo: TeamRepository,
        guard: StudentOperationGuard,
        student_validator: StudentValidator,
        db: AsyncSession,
    ):
        """
        Inject all dependencies.
        
        Args:
            student_repo: For student queries
            contest_repo: For contest queries
            team_repo: For team queries
            guard: To check permissions
            student_validator: To validate business rules
            db: Database session
        """
        self.student_repo = student_repo
        self.contest_repo = contest_repo
        self.team_repo = team_repo
        self.guard = guard
        self.validator = student_validator
        self.db = db

    async def get_public_contests(
        self,
        search_term: str | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 10,
    ) -> tuple[int, list[StudentPublicContestResponse]]:
        """
        Get public contests.
        
        FLOW:
        1. Create filter DTO
        2. Call REPOSITORY to query database
        3. Convert to response schema
        4. Return
        
        Args:
            search_term: Search filter
            status: Status filter
            skip: Pagination
            limit: Pagination
            
        Returns:
            (total_count, list_of_response_objects)
        """
        try:
            logger.info(
                f"Service: Getting public contests (search={search_term}, status={status})"
            )

            # STEP 1: Create DTO
            filters = PublicContestFilterData(
                search_term=search_term,
                status=status,
                skip=skip,
                limit=limit,
            )

            # STEP 2: Query database via REPOSITORY
            total, contests = await self.student_repo.get_public_contests(filters)

            # STEP 3: Convert to response schema
            responses = [
                StudentPublicContestResponse.model_validate(contest)
                for contest in contests
            ]

            logger.info(f"Service: Retrieved {len(responses)} public contests")

            return total, responses

        except Exception as e:
            logger.error(f"Service: Error getting public contests: {str(e)}")
            raise

    async def get_public_contest_by_id(
        self, contest_id: UUID
    ) -> StudentPublicContestResponse:
        """
        Get single public contest.
        
        FLOW:
        1. Query database via REPOSITORY
        2. Check if found
        3. Convert to response schema
        4. Return
        
        Args:
            contest_id: Contest ID
            
        Returns:
            StudentPublicContestResponse
            
        Raises:
            ContestNotFoundError: If not found
        """
        try:
            logger.info(f"Service: Getting public contest {contest_id}")

            # STEP 1: Query database
            contest = await self.student_repo.get_public_contest_by_id(contest_id)

            # STEP 2: Check if found
            if not contest:
                raise ContestNotFoundError(str(contest_id))

            # STEP 3: Convert to response
            response = StudentPublicContestResponse.model_validate(contest)

            logger.info(f"Service: Retrieved contest {contest_id}")

            return response

        except ContestNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Service: Error getting contest {contest_id}: {str(e)}")
            raise

    async def register_in_contest(
        self,
        student_id: UUID,
        contest_id: UUID,
        team_data: TeamCreate,
    ) -> StudentContestRegistrationResponse:
        """
        Register student in contest.
        
        FLOW:
        1. GUARD: Check if student CAN register
        2. VALIDATOR: Check if team data is valid
        3. REPOSITORY: Get contest details
        4. SERVICE: Create team (calls TeamService)
        5. Convert to response
        6. Return
        
        Args:
            student_id: Student ID
            contest_id: Contest ID
            team_data: Team creation data
            
        Returns:
            StudentContestRegistrationResponse
            
        Raises:
            PermissionDeniedError: If not allowed
            ContestNotFoundError: If contest not found
        """
        try:
            logger.info(
                f"Service: Registering student {student_id} in contest {contest_id}"
            )

            # STEP 1: GUARD - Check permissions
            logger.info("Service: Checking if student can register...")
            await self.guard.can_register_in_contest(student_id, contest_id)
            logger.info("Service: Guard check passed ✓")

            # STEP 2: VALIDATOR - Check business rules
            logger.info("Service: Validating team data...")
            self.validator.validate_team_name(team_data.name)
            if team_data.members:
                self.validator.validate_member_emails(team_data.members)
                self.validator.validate_team_size(len(team_data.members))
            logger.info("Service: Team data validation passed ✓")

            # STEP 3: Get contest details
            logger.info("Service: Fetching contest details...")
            contest = await self.contest_repo.get_contest_by_id(contest_id)
            if not contest:
                raise ContestNotFoundError(str(contest_id))
            logger.info("Service: Contest found ✓")

            # STEP 4: Create team
            logger.info("Service: Creating team...")
            team_validator = TeamValidator()
            team_service = TeamService(
                self.team_repo,
                self.contest_repo,
                guard=None,
                validator=team_validator,
            )
            
            created_team = await team_service.create_team(
                contest_id=contest_id,
                team_data=team_data,
                user_id=student_id,
            )
            logger.info(f"Service: Team created {created_team.id} ✓")

            # STEP 5: Create response
            response = StudentContestRegistrationResponse(
                team_id=created_team.id,
                team_name=created_team.name,
                contest_id=contest.id,
                contest_name=contest.name,
                registration_date=created_team.created_at,
            )

            logger.info(
                f"Service: Registration completed for student {student_id} "
                f"in contest {contest_id}"
            )

            return response

        except PermissionDeniedError as e:
            logger.warning(f"Service: Permission denied: {str(e)}")
            raise
        except ContestNotFoundError as e:
            logger.warning(f"Service: Contest not found: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Service: Registration failed: {str(e)}")
            raise

    async def get_my_registered_contests(
        self,
        student_id: UUID,
        skip: int = 0,
        limit: int = 10,
    ) -> tuple[int, list[StudentRegisteredContestResponse]]:
        """
        Get contests where student is registered.
        
        FLOW:
        1. REPOSITORY: Query contests where student is in a team
        2. Convert each to response schema
        3. Return
        
        Args:
            student_id: Student ID
            skip: Pagination
            limit: Pagination
            
        Returns:
            (total_count, list_of_response_objects)
        """
        try:
            logger.info(f"Service: Getting registered contests for student {student_id}")

            # STEP 1: Query database
            total, contests_with_teams = await self.student_repo.get_student_registered_contests(
                student_id, skip, limit
            )

            # STEP 2: Convert to response schema
            responses = []
            for item in contests_with_teams:
                contest = item["contest"]
                team = item["team"]
                team_status = item["team_status"]

                response = StudentRegisteredContestResponse(
                    id=contest.id,
                    name=contest.name,
                    description=contest.description,
                    status=contest.status.value,
                    start_time=contest.start_time,
                    end_time=contest.end_time,
                    team_id=team.id,
                    team_name=team.name,
                    team_status=team_status.value,
                )
                responses.append(response)

            logger.info(f"Service: Retrieved {len(responses)} registered contests")

            return total, responses

        except Exception as e:
            logger.error(f"Service: Error getting registered contests: {str(e)}")
            raise