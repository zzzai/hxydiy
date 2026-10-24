export function mediaPreviewSource(url?: string): { authenticated: boolean; url: string } | undefined {
  if (!url) return undefined;
  // Only protected media uses the API client and its authorization header.
  if (/^\/(?:api\/v1\/)?admin\/media\/\d+\/content(?:\?|$)/.test(url)) {
    return { authenticated: true, url: url.replace(/^\/api\/v1/, '') };
  }
  if (/^\/?assets\//.test(url)) return { authenticated: false, url: '/diy/' + url.replace(/^\//, '') };
  return { authenticated: false, url };
}
