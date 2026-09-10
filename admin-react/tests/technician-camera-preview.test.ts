import assert from 'node:assert/strict';
import test from 'node:test';
import { attachCameraPreview } from '../src/technician/cameraPreview.ts';

test('摄像头流在视频节点出现后挂载并开始播放', async () => {
  const stream = {} as MediaStream;
  let played = false;
  const video = {
    srcObject: null as MediaProvider | null,
    play: async () => { played = true; },
  } as Pick<HTMLVideoElement, 'srcObject' | 'play'>;

  await attachCameraPreview(video, stream);

  assert.equal(video.srcObject, stream);
  assert.equal(played, true);
});
