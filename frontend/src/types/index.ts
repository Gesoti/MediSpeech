export interface Case {
  id: string;
  user_id: string;
  pet_species: string;
  pet_breed: string;
  study_type: string;
  created_at: string;
  updated_at: string;
}

export interface CaseCreate {
  pet_species: string;
  pet_breed: string;
  study_type: string;
}

export interface CaseUpdate {
  pet_species?: string;
  pet_breed?: string;
  study_type?: string;
}

export interface AudioFile {
  id: string;
  case_id: string;
  raw_audio_url: string;
  duration_seconds: number | null;
  created_at: string;
}

export interface Transcription {
  id: string;
  audio_file_id: string;
  raw_text: string;
  confidence: number | null;
  model_used: string;
  created_at: string;
}

export interface Report {
  id: string;
  case_id: string;
  transcription_id: string;
  clinical_history: string | null;
  findings: string | null;
  impressions: string | null;
  recommendations: string | null;
  status: "draft" | "final";
  created_at: string;
  updated_at: string;
}

export interface ReportCreate {
  transcription_id: string;
}

export interface ReportUpdate {
  clinical_history?: string | null;
  findings?: string | null;
  impressions?: string | null;
  recommendations?: string | null;
  status?: string | null;
}

export interface StreamedReportSave {
  clinical_history?: string | null;
  findings?: string | null;
  impressions?: string | null;
  recommendations?: string | null;
}

export type ReportSection = "clinical_history" | "findings" | "impressions" | "recommendations";

export interface StreamEvent {
  section?: ReportSection;
  status?: "start" | "done" | "complete";
  token?: string;
  text?: string;
  clinical_history?: string;
  findings?: string;
  impressions?: string;
  recommendations?: string;
  error?: string;
}
