import argparse
import asyncio
import json
import logging
import os
import ssl
import uuid

import numpy as np

import cv2
from aiohttp import web
from av import VideoFrame

from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder, MediaRelay

ROOT = os.path.dirname(__file__)

logger = logging.getLogger("pc")
pcs = set()
relay = MediaRelay()
#  vid = cv2.VideoCapture(0)


class VideoTransformTrack(MediaStreamTrack):
    """
    A video stream track that transforms frames from an another track.
    """

    kind = "video"

    def __init__(self, track, transform, webcamPlayer):
        super().__init__()  # don't forget this!
        self.track = track
        self.transform = transform
        self.webcamPlayer = webcamPlayer

    async def recv(self):

        #  ret, frame2 = vid.read()

        #  https://stackoverflow.com/questions/43665208/how-to-get-the-latest-frame-from-capture-device-camera-in-opencv

        #  print("frame2: ")
        #  print(frame2)

        #  print(self.webcamPlayer.video)
        frame = await self.track.recv()
        img = frame.to_ndarray(format="bgr24")

        frame2 = await self.webcamPlayer.video.recv()
        img2 = frame2.to_ndarray(format="bgr24")

        try:
            img = np.concatenate((img, img2), axis=1)
        except Exception as e:
            pass

        #  frame = await self.webcamPlayer.video.recv()
        #  img = frame.to_ndarray(format="bgr24")

        new_frame = VideoFrame.from_ndarray(img, format="bgr24")
        new_frame.pts = frame.pts
        new_frame.time_base = frame.time_base
        return new_frame


async def index(request):
    content = open(os.path.join(ROOT, "index.html"), "r").read()
    return web.Response(content_type="text/html", text=content)


async def javascript(request):
    content = open(os.path.join(ROOT, "client.js"), "r").read()
    return web.Response(content_type="application/javascript", text=content)


async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pc_id = "PeerConnection(%s)" % uuid.uuid4()
    pcs.add(pc)

    def log_info(msg, *args):
        logger.info(pc_id + " " + msg, *args)

    log_info("Created for %s", request.remote)

    # prepare local media
    player = MediaPlayer(os.path.join(ROOT, "demo-instruct.wav"))
    if args.record_to:
        recorder = MediaRecorder(args.record_to)
    else:
        recorder = MediaBlackhole()

    # Open webcam on OS X.
    webcamPlayer = MediaPlayer('default:none', format='avfoundation', options={
        'framerate': '30',
        'video_size': '640x480'
    })


    @pc.on("datachannel")
    def on_datachannel(channel):
        @channel.on("message")
        def on_message(message):
            if isinstance(message, str) and message.startswith("ping"):
                channel.send("pong" + message[4:])

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        log_info("Connection state is %s", pc.connectionState)
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    @pc.on("track")
    def on_track(track):
        log_info("Track %s received", track.kind)

        if track.kind == "audio":
            pc.addTrack(player.audio)
            recorder.addTrack(track)
        elif track.kind == "video":

            pc.addTrack(
                VideoTransformTrack(
                    relay.subscribe(track), transform=params["video_transform"], webcamPlayer=webcamPlayer)
            )
            if args.record_to:
                recorder.addTrack(relay.subscribe(track))

        @track.on("ended")
        async def on_ended():
            log_info("Track %s ended", track.kind)
            await recorder.stop()

    # handle offer
    await pc.setRemoteDescription(offer)
    await recorder.start()

    # send answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )


async def on_shutdown(app):
    # close peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()


#  async def renderOpencv(): 

#      while True: 
#          ret, frame = vid.read()

#          # Display the resulting frame
#          cv2.imshow('frame', frame)

#          if cv2.waitKey(1) & 0xFF == ord('q'):
#              break

#          await asyncio.sleep(0.1)

#  async def start_background_tasks(app): 
#      app['opencv_renderer'] = asyncio.create_task(renderOpencv())

#  async def cleanup_background_tasks(app): 
#      app['opencv_renderer'].cancel()
#      await app['opencv_renderer'] 


#  async def main(): 
#      parser = argparse.ArgumentParser(
#          description="WebRTC audio / video / data-channels demo"
#      )
#      parser.add_argument("--cert-file", help="SSL certificate file (for HTTPS)")
#      parser.add_argument("--key-file", help="SSL key file (for HTTPS)")
#      parser.add_argument(
#          "--host", default="0.0.0.0", help="Host for HTTP server (default: 0.0.0.0)"
#      )
#      parser.add_argument(
#          "--port", type=int, default=8080, help="Port for HTTP server (default: 8080)"
#      )
#      parser.add_argument("--record-to", help="Write received media to a file."),
#      parser.add_argument("--verbose", "-v", action="count")

#      args = parser.parse_args()

#      if args.verbose:
#          logging.basicConfig(level=logging.DEBUG)
#      else:
#          logging.basicConfig(level=logging.INFO)

#      if args.cert_file:
#          ssl_context = ssl.SSLContext()
#          ssl_context.load_cert_chain(args.cert_file, args.key_file)
#      else:
#          ssl_context = None

#      app = web.Application()
#      app.on_startup.append(start_background_tasks)
#      app.on_cleanup.append(cleanup_background_tasks)
#      app.on_shutdown.append(on_shutdown)
#      app.router.add_get("/", index)
#      app.router.add_get("/client.js", javascript)
#      app.router.add_post("/offer", offer)
#      web.run_app(
#          app, access_log=None, host=args.host, port=args.port, ssl_context=ssl_context
#      )




if __name__ == "__main__":
    #  asyncio.run(main())
    parser = argparse.ArgumentParser(
        description="WebRTC audio / video / data-channels demo"
    )
    parser.add_argument("--cert-file", help="SSL certificate file (for HTTPS)")
    parser.add_argument("--key-file", help="SSL key file (for HTTPS)")
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host for HTTP server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port for HTTP server (default: 8080)"
    )
    parser.add_argument("--record-to", help="Write received media to a file."),
    parser.add_argument("--verbose", "-v", action="count")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.cert_file:
        ssl_context = ssl.SSLContext()
        ssl_context.load_cert_chain(args.cert_file, args.key_file)
    else:
        ssl_context = None

    app = web.Application()
    #  app.on_startup.append(start_background_tasks)
    #  app.on_cleanup.append(cleanup_background_tasks)
    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/", index)
    app.router.add_get("/client.js", javascript)
    app.router.add_post("/offer", offer)
    web.run_app(
        app, access_log=None, host=args.host, port=args.port, ssl_context=ssl_context
    )

