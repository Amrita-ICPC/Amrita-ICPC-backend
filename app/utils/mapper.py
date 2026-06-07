from app.core.clients.judge0 import Judge0StatusCode
from app.utils.enums import SubmissionStatus

JUDGE0_TO_SUBMISSION_STATUS = {
    Judge0StatusCode.ACCEPTED: SubmissionStatus.AC,
    Judge0StatusCode.COMPILATION_ERROR: SubmissionStatus.CE,
    Judge0StatusCode.WRONG_ANSWER: SubmissionStatus.WA,
    Judge0StatusCode.TIME_LIMIT_EXCEEDED: SubmissionStatus.TLE,
    Judge0StatusCode.RUNTIME_ERROR_SIGSEGV: SubmissionStatus.RE,
    Judge0StatusCode.RUNTIME_ERROR_SIGXFSZ: SubmissionStatus.RE,
    Judge0StatusCode.RUNTIME_ERROR_SIGFPE: SubmissionStatus.RE,
    Judge0StatusCode.RUNTIME_ERROR_SIGABRT: SubmissionStatus.RE,
    Judge0StatusCode.RUNTIME_ERROR_NZEC: SubmissionStatus.RE,
    Judge0StatusCode.RUNTIME_ERROR_OTHER: SubmissionStatus.RE,
    Judge0StatusCode.INTERNAL_ERROR: SubmissionStatus.SYSTEM_ERROR,
    Judge0StatusCode.EXEC_FORMAT_ERROR: SubmissionStatus.RE,
}
