from app.repositories.student.contest import StudentContestRepository
from uuid import UUID
from app.repositories.contest import ContestRepository
from app.repositories.dto.pagination import PaginationParams
from app.repositories.dto.student.contests import StudentContestFilters
from app.schema.contest import ContestSummaryResponse
from app.schema.student.contests import StudentContestRegistrationRequest, StudentContestListResponse
from app.core.cache.decorators import cache_get
from app.mappers.student.contest_mappers import to_student_available_contests_list_response
from app.utils.contest import compute_run_status


class StudentContestService:
    def __init__(self, repository: StudentContestRepository) -> None:
        self.repository = repository

    @cache_get(
        key_builder=lambda self, user_id, request, search, pagination: 
        f"student:contests:user:{user_id}:reg:{request.registered}:status:{','.join(request.status) if request.status else 'any'}:search:{search or 'none'}:skip:{pagination.skip}:limit:{pagination.limit}:min_team:{request.min_team_size}:max_team:{request.max_team_size}",
        ttl=300
    )
    async def get_all_contests(
        self,
        user_id: UUID,
        request: StudentContestRegistrationRequest,
        search: str | None,
        pagination: PaginationParams,
    ) -> StudentContestListResponse:
        """
        Retrieve all available contests for a student with filtering and pagination.
        """
        filters = StudentContestFilters(
            search_term=search,
            registered=request.registered,
            run_statuses=request.status,
            min_team_size=request.min_team_size,
            max_team_size=request.max_team_size,
        )

        paginated_result, teams_count_dict = await self.repository.get_student_contests(
            user_id=user_id,
            filters=filters,
            pagination=pagination,
        )

        return to_student_available_contests_list_response(
            paginated_result,
            skip=pagination.skip,
            limit=pagination.limit,
            teams_count_dict=teams_count_dict,
            run_status_calculator=compute_run_status
        )

    async def get_contest_by_id(self, contest_id: UUID):
        pass
