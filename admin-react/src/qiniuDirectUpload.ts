export type QiniuUploadObserver<Result> = {
  next: (progress: { total: { percent: number } }) => void;
  error: (error: Error) => void;
  complete: (result: Result) => void;
};

export type QiniuUploadObservable<Result> = {
  subscribe: (observer: QiniuUploadObserver<Result>) => { unsubscribe: () => void };
};

export function waitForQiniuUpload<Result>(
  observable: QiniuUploadObservable<Result>,
  onProgress?: (percent: number) => void,
): Promise<Result> {
  return new Promise((resolve, reject) => {
    observable.subscribe({
      next: (progress) => onProgress?.(progress.total.percent),
      error: reject,
      complete: resolve,
    });
  });
}
