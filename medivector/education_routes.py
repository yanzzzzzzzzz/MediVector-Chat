from uuid import UUID
from fastapi import APIRouter
from . import education
from .education_schemas import GenerateDraft, EditDraft, DraftTransition, SourceFeedback

router = APIRouter(prefix='/api/education', tags=['Education review workspace'])


@router.post('/drafts', status_code=201)
def generate(payload: GenerateDraft):
    return education.generate(payload)


@router.get('/drafts')
def drafts():
    return {'drafts': education.list_drafts()}


@router.get('/drafts/{draft_id}')
def draft(draft_id: UUID):
    return education.get_draft(draft_id)


@router.post('/drafts/{draft_id}/revisions')
def edit(draft_id: UUID, payload: EditDraft):
    return education.edit(draft_id, payload)


@router.post('/drafts/{draft_id}/transition')
def transition(draft_id: UUID, payload: DraftTransition):
    return education.transition(draft_id, payload)


@router.post('/feedback', status_code=201)
def feedback(payload: SourceFeedback):
    return education.feedback(payload)


@router.get('/feedback')
def reports():
    return {'feedback': education.list_feedback()}
