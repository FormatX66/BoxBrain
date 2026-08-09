"""Local one-shot rescue control page."""

from __future__ import annotations

from html import escape


def render_rescue_page(csrf_token: str) -> str:
    token = escape(csrf_token, quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>BoxBrain One-Shot Rescue</title>
  <style>
    :root {{ color-scheme: dark; font-family: system-ui,sans-serif; }}
    body {{ margin:0; background:#08110e; color:#e9fff5; }}
    main {{ max-width:900px; margin:auto; padding:24px; }}
    section {{ background:#102019; border:1px solid #284437; border-radius:16px; padding:18px; margin:14px 0; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }}
    label {{ display:block; color:#9bb7aa; margin:9px 0 4px; }}
    input,select,button {{ width:100%; box-sizing:border-box; border-radius:9px; border:1px solid #426554; padding:10px; background:#091611; color:#e9fff5; }}
    button {{ margin-top:10px; cursor:pointer; font-weight:700; }}
    button:hover {{ border-color:#8fffc0; }}
    .danger {{ border-color:#8b3d49; }}
    pre {{ white-space:pre-wrap; overflow-wrap:anywhere; background:#06100c; border-radius:10px; padding:12px; }}
    a {{ color:#8fffc0; }}
  </style>
</head>
<body><main>
  <h1>BoxBrain One-Shot Rescue</h1>
  <p><a href="/">Back to BoxBrain</a></p>
  <section>
    <h2>State</h2>
    <pre id="state">Loading...</pre>
    <button id="refresh">Refresh status, images, and hardware</button>
  </section>
  <section>
    <h2>Arm exactly one rescue boot</h2>
    <div class="grid">
      <div><label for="mode">Mode</label><input id="mode" value="rescue:kali"></div>
      <div><label for="architecture">Target architecture</label><select id="architecture"><option>x86_64</option><option>arm64</option><option>multi</option></select></div>
    </div>
    <label for="confirmation">Exact confirmation</label>
    <input id="confirmation" autocomplete="off" placeholder="ARM ONE-SHOT RESCUE">
    <button id="arm">Arm one-shot rescue</button>
  </section>
  <section>
    <h2>Cancel or return to normal</h2>
    <label for="normal-confirmation">Exact confirmation</label>
    <input id="normal-confirmation" autocomplete="off" placeholder="CANCEL ONE-SHOT RESCUE">
    <button id="cancel">Cancel armed rescue</button>
    <button id="normal" class="danger">Select NORMAL BOXBRAIN (preview; no reboot)</button>
  </section>
  <section><h2>Result</h2><pre id="result">No action requested.</pre></section>
  <script>
    const token = "{token}";
    const state = document.getElementById("state");
    const result = document.getElementById("result");
    async function getJson(path) {{
      const response = await fetch(path, {{cache:"no-store"}});
      const body = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(body));
      return body;
    }}
    async function refresh() {{
      try {{
        const [status,images,hardware] = await Promise.all([
          getJson("/api/v1/rescue/status"),
          getJson("/api/v1/rescue/images"),
          getJson("/api/v1/rescue/hardware")
        ]);
        state.textContent = JSON.stringify({{status,images,hardware}}, null, 2);
      }} catch (error) {{ state.textContent = String(error); }}
    }}
    async function control(payload) {{
      result.textContent = "Working...";
      try {{
        const response = await fetch("/api/v1/rescue/control", {{
          method:"POST",
          headers:{{"Content-Type":"application/json","X-BoxBrain-CSRF":token}},
          body:JSON.stringify(payload)
        }});
        const body = await response.json();
        if (!response.ok) throw new Error(JSON.stringify(body));
        result.textContent = JSON.stringify(body, null, 2);
        await refresh();
      }} catch (error) {{ result.textContent = String(error); }}
    }}
    document.getElementById("refresh").onclick = refresh;
    document.getElementById("arm").onclick = () => control({{
      action:"arm", mode:document.getElementById("mode").value,
      target_architecture:document.getElementById("architecture").value,
      confirmation:document.getElementById("confirmation").value
    }});
    document.getElementById("cancel").onclick = () => control({{
      action:"cancel", confirmation:document.getElementById("normal-confirmation").value
    }});
    document.getElementById("normal").onclick = () => control({{
      action:"reboot-normal", execute:false,
      confirmation:document.getElementById("normal-confirmation").value
    }});
    refresh();
  </script>
</main></body></html>"""
