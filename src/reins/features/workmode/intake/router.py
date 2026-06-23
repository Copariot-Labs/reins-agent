from reins.features.workmode.intake.schema import ResidentIssue


def route_issue(issue: ResidentIssue) -> str:
    """
    Maps intake → WorkMode execution path
    """

    if issue.issue_type == "safety":
        return "emergency_workflow"

    if issue.issue_type == "repair":
        return "office_workflow"

    if issue.issue_type == "complaint":
        return "case_management_workflow"

    return "general_workflow"