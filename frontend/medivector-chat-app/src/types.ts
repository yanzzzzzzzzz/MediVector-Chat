export interface Embedding {
  dimension: number
  preview: number[]
  values: number[]
}

export interface DocumentItem {
  uuid: string
  document_id: string
  source_id: number | string
  title: string
  source: string
  publisher?: string
  published_date?: string
  version?: string
  audience?: string
  topic?: string
  credibility?: string
  content: string
  file_name?: string | null
  file_object_key?: string | null
  file_bucket?: string | null
  file_content_type?: string | null
  file_size?: number | null
  chunk_index?: number | null
  chunk_count?: number | null
  created_at: string
  updated_at?: string
  embedding?: Embedding
}

export interface DocumentGroup {
  document_id: string
  source_id: number | string
  title: string
  source: string
  publisher: string
  published_date: string
  version: string
  audience: string
  topic: string
  credibility: string
  file_name: string
  file_object_key: string
  file_bucket: string
  created_at: string
  updated_at: string
  chunk_count: number
  chunks: DocumentItem[]
  content: string
}

export interface DocumentSection {
  key: string
  label: string
  groups: DocumentGroup[]
}

export interface MetadataSuggestions {
  title: string
  published_date: string
  audience: string
  topic: string
}

export interface ReferenceItem {
  index: number
  uuid: string
  document_id: string
  source_id: number
  title: string
  source: string
  publisher?: string
  published_date?: string
  version?: string
  audience?: string
  topic?: string
  credibility?: string
  content: string
  distance: number | null
  distance_text: string
}

export interface RiskAssessment {
  level: 'green' | 'yellow' | 'red'
  label: string
  reason: string
  diverted: boolean
  action: string
}

export interface EvidenceAssessment {
  sufficient: boolean
  reason: string
  reference_count: number
  best_distance: number | null
}

export interface AskResponse {
  answer: string
  rag_enabled: boolean
  references: ReferenceItem[]
  evidence_assessment?: EvidenceAssessment
  retrieval_terms?: string[]
  memory_messages: number
  risk_assessment?: RiskAssessment
}

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  text: string
  references: ReferenceItem[]
  evidenceAssessment?: EvidenceAssessment | null
  retrievalTerms?: string[]
  riskAssessment?: RiskAssessment | null
  thinking?: boolean
}

export interface AnswerPart {
  text?: string
  ref?: ReferenceItem
}

export interface ConversationItem {
  id: string
  title: string
  created_at: string
}

export interface ConversationMessageItem {
  role: string
  content: string
  references?: ReferenceItem[]
  evidence_assessment?: EvidenceAssessment | null
  retrieval_terms?: string[]
  risk_assessment?: RiskAssessment | null
}
