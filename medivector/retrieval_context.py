from dataclasses import dataclass
from datetime import datetime, timezone
from .api_auth import Principal, current_principal
from .knowledge import KnowledgeError


@dataclass(frozen=True)
class RetrievalContext:
    principal: Principal
    branch_id: str
    department_id: str
    query_at: datetime

    def payload(self):
        return {"organization_id": self.principal.organization_id,
                "branch_id": self.branch_id, "department_id": self.department_id,
                "role": self.principal.role, "query_at": self.query_at.isoformat(),
                "status": "approved", "validity": "effective_from <= query_at < effective_until",
                "acl": "server principal role and named-user grants", "strategy": "exact_over_authorized_subset"}


def context_for_request(branch_id=None, department_id=None):
    principal = current_principal.get()
    if not principal or not principal.organization_id:
        if branch_id or department_id:
            raise KnowledgeError("Institutional filters require an organization account", 403)
        return None
    if not branch_id or not department_id:
        raise KnowledgeError("Select an authorized branch_id and department_id")
    if branch_id not in principal.branch_ids or department_id not in principal.department_ids:
        raise KnowledgeError("Requested scope is outside the account grants", 403)
    return RetrievalContext(principal, branch_id, department_id, datetime.now(timezone.utc))
