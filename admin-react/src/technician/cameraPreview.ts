export async function attachCameraPreview(
  video: Pick<HTMLVideoElement, 'srcObject' | 'play'>,
  stream: MediaStream,
) {
  video.srcObject = stream;
  await video.play();
}
