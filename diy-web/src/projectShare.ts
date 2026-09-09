export type ProjectShareOutcome = 'shared' | 'copied' | 'dismissed' | 'unavailable';

type SharePort = {
  share?: (data: ShareData) => Promise<void>;
  writeText?: (text: string) => Promise<void>;
};

export function createProjectShareUrl(currentUrl: string, projectCode: string): string {
  const current = new URL(currentUrl);
  const shared = new URL(`/share/project/${encodeURIComponent(projectCode)}`, current.origin);
  const storeId = current.searchParams.get('store');
  if (storeId) shared.searchParams.set('store', storeId);
  return shared.toString();
}

export async function shareProjectLink(input: { currentUrl: string; projectCode: string; projectName: string }, port: SharePort): Promise<ProjectShareOutcome> {
  const url = createProjectShareUrl(input.currentUrl, input.projectCode);
  const data: ShareData = {
    title: `荷小悦 · ${input.projectName}`,
    text: `推荐您看看荷小悦的${input.projectName}`,
    url,
  };
  if (port.share) {
    try {
      await port.share(data);
      return 'shared';
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') return 'dismissed';
    }
  }
  if (port.writeText) {
    await port.writeText(url);
    return 'copied';
  }
  return 'unavailable';
}
