import assert from 'node:assert/strict';
import test from 'node:test';
import { waitForQiniuUpload } from '../src/qiniuDirectUpload.ts';

test('waitForQiniuUpload forwards progress and resolves only after the SDK completes', async () => {
  const progress: number[] = [];
  const result = await waitForQiniuUpload({
    subscribe(observer) {
      observer.next({ total: { percent: 25 } });
      observer.next({ total: { percent: 100 } });
      observer.complete({ key: 'stores/1/media/staging/cover.png' });
      return { unsubscribe() {} };
    },
  }, (percent) => progress.push(percent));

  assert.deepEqual(progress, [25, 100]);
  assert.deepEqual(result, { key: 'stores/1/media/staging/cover.png' });
});

test('waitForQiniuUpload rejects when the SDK reports an upload error', async () => {
  await assert.rejects(
    waitForQiniuUpload({
      subscribe(observer) {
        observer.error(new Error('network failed'));
        return { unsubscribe() {} };
      },
    }),
    /network failed/,
  );
});
