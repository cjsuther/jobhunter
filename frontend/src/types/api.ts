export type Job = {
  id: string;
  source_portal: string;
  external_id: string;
  external_url: string;
  title: string;
  company: string | null;
  location: string | null;
  modality: string | null;
  description: string | null;
  posted_at: string | null;
  scraped_at: string;
  application_type: string | null;
};

export type Material = {
  id: string;
  type: "cv" | "cover_letter";
  content_md: string;
  pdf_path: string | null;
  version: number;
  model_used: string | null;
  generated_at: string;
};

export type Match = {
  id: string;
  job: Job;
  profile_id: string;
  profile_name: string;
  fit_score: number;
  recommended_action: "apply" | "review" | "skip" | null;
  strengths: string[] | null;
  red_flags: string[] | null;
  status: string;
  scored_at: string;
};

export type MatchDetail = Match & {
  scoring_reasoning: string | null;
  user_notes: string | null;
  materials: Material[];
};

export type Criteria = {
  id: string;
  user_id: string;
  profile_id: string;
  name: string | null;
  keywords: string[];
  locations: string[];
  modalities: string[];
  seniority_levels: string[];
  salary_min_ars: number | null;
  contract_types: string[];
  min_fit_score: number;
  daily_apply_cap: number;
  active: boolean;
  portals_enabled: string[];
};

export type ProfileSummary = {
  id: string;
  name: string;
  headline: string | null;
  has_cv: boolean;
};

export type Profile = {
  id: string;
  user_id: string;
  name: string;
  full_name: string | null;
  headline: string | null;
  current_location: string | null;
  years_experience: number | null;
  linkedin_url: string | null;
  phone: string | null;
  email_contact: string | null;
  cv_base_json: Record<string, unknown>;
  cv_base_pdf_path: string | null;
  about_text: string | null;
  preferred_titles: string[] | null;
  excluded_companies: string[] | null;
  excluded_keywords: string[] | null;
};

export type Funnel = {
  scored: number;
  above_threshold: number;
  approved: number;
  applied: number;
  responded: number;
  interview: number;
  offer: number;
};
