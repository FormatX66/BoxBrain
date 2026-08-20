#!/usr/bin/env python3
"""Hopper's first Aurum arcade proof: Echo Rally.

A dependency-free, loopback-only Pong-like game used to exercise rendering,
keyboard/pointer input, timing, sound, and application lifecycle without giving
browser code any host authority.
"""
from __future__ import annotations

import argparse
import json
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

SCHEMA = "aurum.arcade.v1"
GAME = "Echo Rally"
MACHINE = "Hopper"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766

PAGE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<meta name="color-scheme" content="dark">
<title>Echo Rally — Hopper</title>
<style nonce="{{NONCE}}">
:root{--bg:#07090e;--ink:#f7f1df;--muted:#8e96a7;--gold:#f5c451;--echo:#77d7d3;--line:rgba(245,196,81,.25)}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:var(--bg);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;overflow:hidden}
body{display:grid;place-items:center;background:radial-gradient(circle at 50% 12%,rgba(245,196,81,.10),transparent 35rem),radial-gradient(circle at 18% 88%,rgba(119,215,211,.08),transparent 34rem),#07090e}
.wrap{width:min(1180px,100vw);height:100vh;display:grid;grid-template-rows:auto 1fr auto;gap:12px;padding:18px}
header{display:flex;align-items:end;justify-content:space-between;gap:18px}.eyebrow{font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--gold)}
h1{font-size:clamp(28px,5vw,54px);letter-spacing:-.05em;margin:3px 0 0}.sub{font-size:12px;color:var(--muted);max-width:580px;line-height:1.45;text-align:right}
.stage{min-height:0;border:1px solid var(--line);border-radius:24px;padding:8px;background:rgba(14,17,25,.82);box-shadow:0 28px 80px rgba(0,0,0,.45)}
canvas{display:block;width:100%;height:100%;border-radius:18px;background:#090c12;touch-action:none;outline:none}
footer{display:flex;justify-content:space-between;gap:16px;color:var(--muted);font-size:11px}.keys{display:flex;gap:14px;flex-wrap:wrap}.key{color:var(--ink)}
.badge{color:var(--echo)}
@media(max-width:700px){.wrap{padding:10px}.sub{display:none}footer{display:block}.keys{margin-bottom:6px}}
</style>
</head>
<body>
<div class="wrap">
<header><div><div class="eyebrow">Hopper · Aurum Arcade 001</div><h1>Echo Rally</h1></div><div class="sub">Pong, except the arena remembers. Every fourth return leaves a temporary echo well; your old paddle choices bend the next rally.</div></header>
<div class="stage"><canvas id="game" width="960" height="540" tabindex="0" aria-label="Echo Rally game"></canvas></div>
<footer><div class="keys"><span><b class="key">W/S</b> left</span><span><b class="key">↑/↓</b> right</span><span><b class="key">1</b> solo</span><span><b class="key">2</b> two-player</span><span><b class="key">P</b> pause</span><span><b class="key">Enter</b> reset</span></div><div class="badge">Echo wells bend the ball, but never decide the winner for you.</div></footer>
</div>
<script nonce="{{NONCE}}">
(() => {
  const canvas=document.getElementById('game'),ctx=canvas.getContext('2d');
  const W=960,H=540,PW=16,PH=112,M=34,WIN=7;
  let mode=1,paused=false,last=performance.now(),rally=0,scoreL=0,scoreR=0,serveDir=1,wells=[],trail=[],audio=null;
  const keys=new Set();
  const left={x:M,y:H/2-PH/2,v:0},right={x:W-M-PW,y:H/2-PH/2,v:0};
  const ball={x:W/2,y:H/2,r:9,vx:390,vy:120};
  function beep(freq,dur=.035,gain=.035){try{audio=audio||new (window.AudioContext||window.webkitAudioContext)();const o=audio.createOscillator(),g=audio.createGain();o.frequency.value=freq;g.gain.value=gain;o.connect(g);g.connect(audio.destination);o.start();o.stop(audio.currentTime+dur)}catch(_){}}
  function resetBall(dir=serveDir){serveDir=dir;ball.x=W/2;ball.y=H/2;const angle=(Math.random()*.7-.35);const speed=380;ball.vx=Math.cos(angle)*speed*dir;ball.vy=Math.sin(angle)*speed;rally=0;trail=[]}
  function resetGame(){scoreL=scoreR=0;wells=[];resetBall(Math.random()<.5?-1:1);paused=false}
  function addWell(x,y){wells.push({x,y,born:performance.now(),life:3600});if(wells.length>4)wells.shift();beep(620,.055,.025)}
  function paddleHit(p,side){const center=p.y+PH/2,offset=(ball.y-center)/(PH/2);const speed=Math.min(760,Math.hypot(ball.vx,ball.vy)*1.045+8);const angle=offset*1.02;ball.vx=Math.cos(angle)*speed*side;ball.vy=Math.sin(angle)*speed;rally++;if(rally%4===0)addWell(ball.x,ball.y);beep(290+rally*9,.025,.03)}
  function clamp(v,a,b){return Math.max(a,Math.min(b,v))}
  function update(dt,now){
    if(paused)return;
    const speed=500;
    left.v=((keys.has('KeyS')?1:0)-(keys.has('KeyW')?1:0))*speed;
    if(mode===2)right.v=((keys.has('ArrowDown')?1:0)-(keys.has('ArrowUp')?1:0))*speed;
    else{const target=ball.y-PH/2;right.v=clamp((target-right.y)*5.1,-390,390)}
    left.y=clamp(left.y+left.v*dt,12,H-PH-12);right.y=clamp(right.y+right.v*dt,12,H-PH-12);
    wells=wells.filter(w=>now-w.born<w.life);
    for(const w of wells){const dx=w.x-ball.x,dy=w.y-ball.y,d2=dx*dx+dy*dy+4000,force=62000/d2;ball.vx+=dx*force*dt;ball.vy+=dy*force*dt}
    ball.x+=ball.vx*dt;ball.y+=ball.vy*dt;
    if(ball.y-ball.r<10&&ball.vy<0){ball.y=10+ball.r;ball.vy*=-1;beep(180,.018,.02)}
    if(ball.y+ball.r>H-10&&ball.vy>0){ball.y=H-10-ball.r;ball.vy*=-1;beep(180,.018,.02)}
    if(ball.vx<0&&ball.x-ball.r<=left.x+PW&&ball.x>left.x&&ball.y>=left.y-8&&ball.y<=left.y+PH+8){ball.x=left.x+PW+ball.r;paddleHit(left,1)}
    if(ball.vx>0&&ball.x+ball.r>=right.x&&ball.x<right.x+PW&&ball.y>=right.y-8&&ball.y<=right.y+PH+8){ball.x=right.x-ball.r;paddleHit(right,-1)}
    if(ball.x<-30){scoreR++;beep(110,.16,.06);if(scoreR>=WIN){paused=true}else resetBall(1)}
    if(ball.x>W+30){scoreL++;beep(880,.10,.05);if(scoreL>=WIN){paused=true}else resetBall(-1)}
    trail.push({x:ball.x,y:ball.y,t:now});while(trail.length&&now-trail[0].t>520)trail.shift();
  }
  function draw(now){
    ctx.clearRect(0,0,W,H);
    const bg=ctx.createLinearGradient(0,0,0,H);bg.addColorStop(0,'#0d111a');bg.addColorStop(1,'#07090e');ctx.fillStyle=bg;ctx.fillRect(0,0,W,H);
    ctx.strokeStyle='rgba(245,196,81,.13)';ctx.setLineDash([8,12]);ctx.beginPath();ctx.moveTo(W/2,26);ctx.lineTo(W/2,H-26);ctx.stroke();ctx.setLineDash([]);
    for(const w of wells){const age=(now-w.born)/w.life,alpha=1-age,r=28+age*110;ctx.strokeStyle=`rgba(119,215,211,${.34*alpha})`;ctx.lineWidth=2;ctx.beginPath();ctx.arc(w.x,w.y,r,0,Math.PI*2);ctx.stroke();ctx.fillStyle=`rgba(119,215,211,${.08*alpha})`;ctx.beginPath();ctx.arc(w.x,w.y,18,0,Math.PI*2);ctx.fill()}
    for(let i=0;i<trail.length;i++){const a=(i+1)/trail.length;ctx.fillStyle=`rgba(245,196,81,${a*.18})`;ctx.beginPath();ctx.arc(trail[i].x,trail[i].y,3+a*3,0,Math.PI*2);ctx.fill()}
    ctx.fillStyle='#f5c451';ctx.shadowColor='rgba(245,196,81,.55)';ctx.shadowBlur=14;ctx.fillRect(left.x,left.y,PW,PH);ctx.fillRect(right.x,right.y,PW,PH);ctx.shadowBlur=0;
    ctx.fillStyle='#fff5cf';ctx.shadowColor='rgba(255,230,160,.8)';ctx.shadowBlur=16;ctx.beginPath();ctx.arc(ball.x,ball.y,ball.r,0,Math.PI*2);ctx.fill();ctx.shadowBlur=0;
    ctx.textAlign='center';ctx.fillStyle='rgba(247,241,223,.92)';ctx.font='700 52px system-ui';ctx.fillText(scoreL,W*.42,70);ctx.fillText(scoreR,W*.58,70);
    ctx.font='600 12px system-ui';ctx.fillStyle='rgba(142,150,167,.9)';ctx.fillText(`${mode===1?'SOLO':'TWO PLAYER'}  ·  RALLY ${rally}  ·  ECHO ${rally%4}/4`,W/2,H-24);
    if(paused){ctx.fillStyle='rgba(7,9,14,.62)';ctx.fillRect(0,0,W,H);ctx.fillStyle='#ffe6a0';ctx.font='750 42px system-ui';const winner=scoreL>=WIN?'LEFT WINS':scoreR>=WIN?'RIGHT WINS':'PAUSED';ctx.fillText(winner,W/2,H/2-8);ctx.fillStyle='#9ea5b5';ctx.font='500 15px system-ui';ctx.fillText(scoreL>=WIN||scoreR>=WIN?'Press Enter for another match':'Press P to continue',W/2,H/2+28)}
  }
  function frame(now){const dt=Math.min(.025,(now-last)/1000);last=now;update(dt,now);draw(now);requestAnimationFrame(frame)}
  addEventListener('keydown',e=>{keys.add(e.code);if(['ArrowUp','ArrowDown','Space'].includes(e.code))e.preventDefault();if(e.code==='Digit1'){mode=1;beep(420)}if(e.code==='Digit2'){mode=2;beep(520)}if(e.code==='KeyP'){paused=!paused;beep(paused?220:440)}if(e.code==='Enter')resetGame()});
  addEventListener('keyup',e=>keys.delete(e.code));
  function pointer(e){const r=canvas.getBoundingClientRect(),x=(e.clientX-r.left)/r.width*W,y=(e.clientY-r.top)/r.height*H;if(x<W/2)left.y=clamp(y-PH/2,12,H-PH-12);else if(mode===2)right.y=clamp(y-PH/2,12,H-PH-12)}
  canvas.addEventListener('pointerdown',e=>{canvas.setPointerCapture(e.pointerId);pointer(e);canvas.focus();beep(350)});canvas.addEventListener('pointermove',e=>{if(e.buttons)pointer(e)});
  canvas.focus();resetBall(1);requestAnimationFrame(frame);
})();
</script>
</body>
</html>'''


class ArcadeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def _loopback_host(self) -> bool:
        try:
            return urlsplit(f"//{self.headers.get('Host','')}").hostname in {"127.0.0.1","localhost","::1"}
        except ValueError:
            return False

    def _headers(self, nonce: str | None = None) -> None:
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), usb=(), serial=()")
        if nonce:
            self.send_header("Content-Security-Policy", f"default-src 'none'; style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")

    def do_GET(self) -> None:  # noqa: N802
        if not self._loopback_host():
            self.send_error(HTTPStatus.BAD_REQUEST)
            return
        path=urlsplit(self.path).path
        if path=="/api/status":
            body=json.dumps({"schema":SCHEMA,"status":"ready","game":GAME,"machine":MACHINE,"loopback_only":True,"host_actuation":False},sort_keys=True).encode()
            self.send_response(HTTPStatus.OK);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(body)));self._headers();self.end_headers();self.wfile.write(body);return
        if path not in {"/","/echo-rally"}:
            self.send_error(HTTPStatus.NOT_FOUND);return
        nonce=secrets.token_urlsafe(18);body=PAGE.replace("{{NONCE}}",nonce).encode("utf-8")
        self.send_response(HTTPStatus.OK);self.send_header("Content-Type","text/html; charset=utf-8");self.send_header("Content-Length",str(len(body)));self._headers(nonce);self.end_headers();self.wfile.write(body)


def main() -> int:
    parser=argparse.ArgumentParser(description="Aurum Echo Rally arcade server")
    parser.add_argument("--host",default=DEFAULT_HOST);parser.add_argument("--port",type=int,default=DEFAULT_PORT)
    args=parser.parse_args()
    if args.host not in {"127.0.0.1","::1"}: raise SystemExit("Arcade must remain loopback-only")
    server=ArcadeServer((args.host,args.port),Handler)
    print(f"AURUM_ARCADE_READY machine={MACHINE} game={GAME!r} address={args.host} port={server.server_address[1]}",flush=True)
    try: server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt: pass
    finally: server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
