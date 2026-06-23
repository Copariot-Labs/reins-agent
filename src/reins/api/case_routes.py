from reins.features.workmode.case_service import CaseService

service = CaseService()


# GET CASE DETAIL
async def get_case_detail(case_id: str):
    return service.replay_case(case_id)


# GET EVENTS ONLY
async def get_case_events(case_id: str):
    return service.get_events(case_id)


# GET ARTIFACTS ONLY
async def get_case_artifacts(case_id: str):
    return service.get_artifacts(case_id)