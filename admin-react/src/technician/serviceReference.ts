export type ServiceArea = 'neck_shoulder' | 'waist_hip' | 'legs' | 'abdomen' | 'feet' | 'full_relaxation';
export type AvoidArea = Exclude<ServiceArea, 'full_relaxation'>;
export type ForcePreference = 'gentle' | 'medium' | 'strong';
export type TemperaturePreference = 'lower' | 'medium' | 'higher';
export type ServiceFeedback = 'suitable' | 'better_after_adjustment' | 'adjust_next_time';
export type NextVisitPlan = 'repeat_current' | 'confirm_on_arrival';

export interface ServiceReferenceInput {
  focusAreas?: ServiceArea[];
  avoidAreas?: AvoidArea[];
  forcePreference?: ForcePreference;
  temperaturePreference?: TemperaturePreference;
  serviceFeedback?: ServiceFeedback;
  nextVisitPlan?: NextVisitPlan;
  customerConfirmed?: boolean;
  quote?: string;
}

const options = <T extends string>(entries: Array<[string, T]>) => entries.map(([label, value]) => ({ label, value }));

export const SERVICE_REFERENCE_OPTIONS = {
  focusAreas: options<ServiceArea>([['肩颈', 'neck_shoulder'], ['腰臀', 'waist_hip'], ['腿部', 'legs'], ['腹部', 'abdomen'], ['足部', 'feet'], ['整体放松', 'full_relaxation']]),
  avoidAreas: options<AvoidArea>([['肩颈', 'neck_shoulder'], ['腰臀', 'waist_hip'], ['腿部', 'legs'], ['腹部', 'abdomen'], ['足部', 'feet']]),
  force: options<ForcePreference>([['轻柔', 'gentle'], ['适中', 'medium'], ['偏强', 'strong']]),
  temperature: options<TemperaturePreference>([['偏低', 'lower'], ['适中', 'medium'], ['偏高', 'higher']]),
  feedback: options<ServiceFeedback>([['本次合适', 'suitable'], ['调整后更合适', 'better_after_adjustment'], ['下次需调整', 'adjust_next_time']]),
  nextVisit: options<NextVisitPlan>([['延续本次', 'repeat_current'], ['到店再确认', 'confirm_on_arrival']]),
} as const;

export function hasServiceReferenceInput(values: ServiceReferenceInput): boolean {
  return Boolean(
    values.focusAreas?.length
    || values.avoidAreas?.length
    || values.forcePreference
    || values.temperaturePreference
    || values.serviceFeedback
    || values.nextVisitPlan
    || values.quote?.trim(),
  );
}

export function buildServiceReferencePayload(userId: number, selectionSessionId: string, values: ServiceReferenceInput) {
  const customerReported: Record<string, unknown> = {};
  if (values.focusAreas) customerReported.focus_areas = values.focusAreas;
  if (values.avoidAreas) customerReported.avoid_areas = values.avoidAreas;
  if (values.forcePreference) customerReported.force_preference = values.forcePreference;
  if (values.temperaturePreference) customerReported.temperature_preference = values.temperaturePreference;
  if (values.quote?.trim()) customerReported.quote = values.quote.trim();
  const confirmed = Boolean(values.customerConfirmed);
  return {
    user_id: userId,
    selection_session_id: selectionSessionId,
    source: confirmed ? 'both' as const : 'service_observation' as const,
    schema_version: 2 as const,
    taxonomy_version: 'service_reference_v1' as const,
    customer_confirmed: confirmed,
    profile: {
      schema_version: 2 as const,
      taxonomy_version: 'service_reference_v1' as const,
      customer_reported: customerReported,
      technician_observed: values.serviceFeedback ? { service_feedback: values.serviceFeedback } : {},
      next_visit: values.nextVisitPlan ? { plan: values.nextVisitPlan } : {},
    },
    signals: [],
    note: '',
  };
}

export interface TechnicianServiceReferenceRecord {
  focus_areas: string[];
  avoid_areas: string[];
  force_preference: string | null;
  temperature_preference: string | null;
  service_feedback: string | null;
  next_visit_plan: string | null;
  confirmed_at: string | null;
  recorded_date: string | null;
  prompt: string;
}

export interface TechnicianServiceReferenceResponse {
  record: TechnicianServiceReferenceRecord | null;
  message: string;
}
