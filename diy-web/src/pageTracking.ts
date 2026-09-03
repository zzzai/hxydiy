type Emit = (event: string, data: Record<string, unknown>) => void;

export function createDiyPageTracking(emit: Emit) {
  return {
    entryView: (data: Record<string, unknown>) => emit('diy_entry_view', data),
    projectView: (data: Record<string, unknown>) => emit('project_view', data),
    projectConfigSave: (data: Record<string, unknown>) => emit('project_config_save', data),
    loginPromptView: (data: Record<string, unknown>) => emit('login_prompt_view', data),
    feedbackView: (data: Record<string, unknown>) => emit('feedback_view', data),
    navigationBack: (data: Record<string, unknown>) => emit('navigation_back', data),
  };
}
