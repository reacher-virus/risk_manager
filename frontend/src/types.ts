export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
export type Status = 'NEW' | 'APPROVED' | 'HELD' | 'ESCALATED'

export interface Contribution { feature: string; label: string; value: number; contribution: number }

export interface Alert {
  transaction_id: string; customer_id: string; amount: number; risk_score: number; risk_level: RiskLevel
  decision: string; reasons: string[]; contributions: Contribution[]; anomaly_score: number
  timestamp: string; source: string; status: Status; label: 'FRAUD' | 'LEGIT' | null
}
export interface AlertList { total: number; threshold: number; items: Alert[] }

export interface TimelineRow { transaction_id: string; timestamp: string; amount: number; risk_score: number; device_id: string; ip_region: string }
export interface RelatedAccount { customer_id: string; transactions: number; max_risk: number; shared_via: string[] }
export interface ReviewEntry { action: string | null; label: string | null; note: string | null; actor: string; at: string }
export interface AlertDetail extends Alert {
  device_id: string; payment_id: string; ip_region: string; merchant_category: string | null; payment_method: string | null
  account_age_days: number; features: Record<string, number>; customer_timeline: TimelineRow[]
  related_accounts: RelatedAccount[]; ring_id: string | null; review_history: ReviewEntry[]
  ground_truth: { is_fraud: number; fraud_pattern: string; synthetic: boolean } | null
}

export interface Summary {
  transactions_analyzed: number; suspicious_transactions: number; high_risk_transactions: number
  estimated_loss_prevented: number; precision: number; recall: number; pr_auc: number; false_positive_rate: number
  threshold: number; live_scored: number; live_flagged: number; open_alerts: number
}
export interface Metrics {
  model_name: string; threshold: number; trained_threshold: number; calibration: string; precision: number; recall: number
  f1: number; pr_auc: number; roc_auc: number | null; false_positive_rate: number; brier_calibrated: number | null
  brier_uncalibrated: number | null; trained_at: string | null; label_delay_days: number | null; dataset_note: string
  val_pr_auc_by_model: Record<string, number>
}
export interface ComparisonSide { precision: number; recall: number; f1: number; pr_auc: number; fp: number; fn: number; fp_cost: number; fn_cost: number }
export interface Comparison { rule_based: ComparisonSide; ml_model: ComparisonSide; model_name: string; cost_reduction_pct: number }

export interface SweepPoint { threshold: number; precision: number; recall: number; fp: number; fn: number; total_cost: number }
export interface ThresholdAnalysis {
  split: string; threshold: number; cost_fp: number; cost_fn: number
  metrics: { precision: number; recall: number; f1: number; false_positive_rate: number; true_positives: number; false_positives: number; true_negatives: number; false_negatives: number }
  cost: { fp: number; fn: number; cost_fp_total: number; cost_fn_total: number; total_cost: number }
  cost_if_no_model: number; optimal_threshold: number; optimal_cost: number; sweep: SweepPoint[]
}

export interface Ring {
  ring_id: string; accounts: number; devices: number; cards: number; transactions: number; total_amount: number
  avg_risk: number; max_risk: number; first_seen: string; last_seen: string; synthetic_fraud_rate?: number
}
export interface GraphNode { id: string; type: 'customer' | 'device' | 'card'; label: string; risk: number; transactions: number }
export interface GraphEdge { source: string; target: string; weight: number }
export interface RingGraph { ring_id: string; nodes: GraphNode[]; edges: GraphEdge[]; summary: Ring | null }

export interface TimePoint { bucket: string; transactions: number; flagged: number; mean_risk: number; synthetic_fraud: number }
export interface BreakdownRow { name: string; transactions: number; flagged: number; flag_rate: number; avg_risk: number; synthetic_fraud_rate: number }
export interface PRCurve { split: string; average_precision: number; base_rate: number; points: { recall: number; precision: number; threshold: number }[] }
export interface Confusion { split: string; threshold: number; true_positives: number; false_positives: number; true_negatives: number; false_negatives: number; precision: number; recall: number; false_positive_rate: number }

export interface DriftFeature { feature: string; psi: number; status: 'stable' | 'watch' | 'retrain' }
export interface Monitoring {
  window: string; score_psi: number; score_status: string; features: DriftFeature[]; retrain_recommended: boolean
  feedback: { labelled_cases: number; confirmed_fraud: number; false_positives: number; analyst_precision: number | null }
  model: { name: string; trained_at: string | null; analyst_rows_in_training: number }
  retrain: { state: string; started?: string; finished?: string; message?: string | null }
}
export interface Config { cost_fp: number; cost_fn: number; threshold: number; trained_threshold: number; label_delay_days: number; role: string; auth_enabled: boolean }
export interface AuditRow { id: number; ts: string; actor: string; action: string; transaction_id: string | null; detail: Record<string, unknown> | null }

export interface PredictResult {
  transaction_id: string; risk_score: number; risk_level: RiskLevel; decision: string; reasons: string[]
  contributions: Contribution[]; anomaly_score: number; novel_pattern: boolean
}
export interface SimResult extends PredictResult { customer_id: string; amount: number; device_id: string }
export type Scenario = 'normal' | 'velocity_burst' | 'fraud_ring' | 'multi_device_ring' | 'account_takeover'

export interface BatchResult {
  result_id: string; rows: number; threshold: number; flagged: number; warnings: string[]
  by_level: Record<RiskLevel, number>; top_alerts: Alert[]
  metrics?: { precision: number; recall: number; f1: number; pr_auc: number; false_positives: number; false_negatives: number }
  cost?: { total_cost: number; cost_fp_total: number; cost_fn_total: number }
}

export type Role = 'viewer' | 'analyst' | 'admin'
export interface User { id: string | null; email: string; full_name: string; role: Role; created_at: string | null; last_login_at: string | null }
export interface Me { authenticated: boolean; via: string; admin_session: boolean; user: User }
export interface CaptchaChallenge { captcha_id: string; image: string; expires_in: number }
export interface Challenge { challenge_id: string; expires_in: number; message: string; mfa_required?: boolean }
export interface AdminUser extends User { status: 'active' | 'disabled'; email_verified: boolean }
