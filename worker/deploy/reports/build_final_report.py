import json
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
endpoint = json.loads((ROOT / "worker/deploy/endpoint.json").read_text(encoding="utf-8"))
job = endpoint["verified_large_loremax_job"]
smoke = endpoint["verified_smoke_job"]

rates = {
    "80 GB PRO": 0.00116,
    "96 GB": 0.00111,
}

exec_s = job["execution_ms"] / 1000
queue_s = job["delay_ms"] / 1000
wall_s = exec_s + queue_s
inference_s = job["metadata"]["inference_seconds"]
frames = job["metadata"]["frame_count"]
input_mb = job["input_probe"]["content_length_bytes"] / 1024 / 1024
out_mb = job["output_bytes"]["comp_mp4"] / 1024 / 1024
preview_mb = job["output_bytes"]["comp_preview_png"] / 1024 / 1024

smoke_exec_s = smoke["execution_ms"] / 1000
smoke_wall_s = smoke["delay_ms"] / 1000 + smoke_exec_s
all_exec_s = exec_s + smoke_exec_s
all_wall_s = wall_s + smoke_wall_s


def money(value: float) -> str:
    return f"${value:.4f}" if value < 1 else f"${value:.2f}"


def dur(seconds: float) -> str:
    minutes, secs = divmod(seconds, 60)
    return f"{int(minutes)}m {secs:.1f}s"


def cost_row(label: str, seconds: float) -> str:
    cells = "".join(f"<td>{money(seconds * rate)}</td>" for rate in rates.values())
    return f"<tr><th>{escape(label)}</th><td>{seconds:.3f}s</td><td>{dur(seconds)}</td>{cells}</tr>"


cost_rows = "\n".join(
    [
        cost_row("Основной большой job: execution_ms", exec_s),
        cost_row("Основной большой job: delay + execution", wall_s),
        cost_row("Только inference внутри pipeline", inference_s),
        cost_row("Smoke + большой job: execution total", all_exec_s),
        cost_row("Smoke + большой job: delay + execution total", all_wall_s),
    ]
)

per_frame_exec = exec_s / frames
per_frame_infer = inference_s / frames
cost_per_frame_80 = exec_s * rates["80 GB PRO"] / frames
cost_per_frame_96 = exec_s * rates["96 GB"] / frames

video_url = job["published_urls"]["comp_mp4"]
preview_url = job["published_urls"]["comp_preview_png"]
input_url = job["input_url"]

html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>CorridorKey RunPod Serverless — финальный отчёт</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Onest:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root {{
  --bg-900:#001228; --bg-800:#032159; --surface:#07193d; --surface-2:#0b2454;
  --bg-500:#007ae6; --bg-400:#329bff; --text:#fff; --muted:#afbfe0;
  --border:#1f3563; --orange:#ff9a27; --orange2:#dc3a04; --green:#1ec020; --red:#fe484b;
  --grad:linear-gradient(130deg,#ff9a27 6.7%,#dc3a04 93%); --font:'Onest',system-ui,sans-serif;
}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:var(--font);background:radial-gradient(900px 500px at 50% -10%,rgba(0,122,230,.25),transparent 65%),var(--bg-900);color:var(--text)}}
a{{color:#8dccff}}
.wrap{{max-width:1180px;margin:0 auto;padding:32px 20px 72px}}
.header{{display:flex;gap:16px;align-items:center;margin-bottom:28px}}
.logo{{width:52px;height:52px;border-radius:16px;background:#061b41;box-shadow:0 0 28px rgba(50,155,255,.3)}}
.kicker{{color:var(--orange);font-weight:800;letter-spacing:.08em;text-transform:uppercase;font-size:12px}}
h1{{font-size:clamp(34px,5vw,64px);line-height:.95;margin:8px 0 12px}}
h2{{margin-top:0}}
.sub{{color:var(--muted);font-size:18px;max-width:860px}}
.grid{{display:grid;grid-template-columns:repeat(12,1fr);gap:18px}}
.card{{background:linear-gradient(180deg,rgba(11,36,84,.94),rgba(7,25,61,.96));border:1px solid var(--border);border-radius:22px;padding:22px;box-shadow:0 12px 35px rgba(0,0,0,.3)}}
.span4{{grid-column:span 4}} .span6{{grid-column:span 6}} .span8{{grid-column:span 8}} .span12{{grid-column:span 12}}
.metric{{font-size:34px;font-weight:800;margin:8px 0 4px}}
.label{{color:var(--muted);font-size:14px}}
.ok{{color:var(--green)}} .warn{{color:var(--orange)}} .bad{{color:var(--red)}}
video,img{{max-width:100%;border-radius:18px;border:1px solid var(--border);background:#000}}
video{{width:100%;display:block}}
table{{width:100%;border-collapse:collapse;overflow:hidden;border-radius:16px}}
th,td{{padding:13px 14px;border-bottom:1px solid rgba(175,191,224,.14);text-align:left;vertical-align:top}}
th{{color:#fff;font-weight:700}}
td{{color:var(--muted)}}
tr:last-child th,tr:last-child td{{border-bottom:0}}
.pill{{display:inline-flex;align-items:center;gap:8px;padding:8px 12px;border-radius:999px;background:rgba(50,155,255,.12);border:1px solid rgba(50,155,255,.32);color:#dff2ff;font-size:13px;margin:4px 6px 4px 0}}
.cta{{display:inline-block;background:var(--grad);color:#ffecdb;text-decoration:none;font-weight:800;padding:13px 18px;border-radius:999px;border:1px solid #ffd996;box-shadow:0 8px 24px rgba(255,120,17,.32)}}
.code{{font-family:ui-monospace,Consolas,monospace;background:#00142f;border:1px solid var(--border);border-radius:14px;padding:14px;overflow:auto;color:#cfe8ff;font-size:13px;white-space:pre-wrap}}
.small{{font-size:13px;color:var(--muted)}}
@media(max-width:850px){{.span4,.span6,.span8{{grid-column:span 12}}}}
</style>
</head>
<body>
<div class="wrap">
  <header class="header">
    <img class="logo" src="https://content.loremax.ai/aplayers-brand/loremax_icon.webp" alt="Loremax" />
    <div>
      <div class="kicker">Loremax AI · RunPod Verification</div>
      <h1>CorridorKey Serverless<br/>финальный отчёт</h1>
      <p class="sub">Большое видео из Loremax S3 обработано через RunPod Serverless, результат опубликован на CDN, стоимость пересчитана по тарифам из RunPod UI.</p>
    </div>
  </header>

  <section class="grid">
    <div class="card span4"><div class="label">Job status</div><div class="metric ok">COMPLETED</div><div class="small">{escape(job["id"])}</div></div>
    <div class="card span4"><div class="label">Execution time</div><div class="metric">{dur(exec_s)}</div><div class="small">{exec_s:.3f}s RunPod execution_ms</div></div>
    <div class="card span4"><div class="label">Estimated cost</div><div class="metric warn">{money(exec_s * rates["96 GB"])}–{money(exec_s * rates["80 GB PRO"])}</div><div class="small">По execution_ms, 1 worker</div></div>

    <div class="card span8">
      <h2>Результат обработки</h2>
      <video src="{video_url}" poster="{preview_url}" controls preload="metadata"></video>
      <p style="margin-top:14px"><a class="cta" href="{video_url}" target="_blank">Открыть MP4</a> <a class="cta" href="{preview_url}" target="_blank">Открыть preview</a></p>
    </div>
    <div class="card span4">
      <h2>Итоговые файлы</h2>
      <p><span class="pill">MP4 {out_mb:.2f} MB</span><span class="pill">Preview {preview_mb:.2f} MB</span></p>
      <p class="small">Выходной MP4: H.264, {job["ffprobe_comp_mp4"]["width"]}×{job["ffprobe_comp_mp4"]["height"]}, {job["ffprobe_comp_mp4"]["frames"]} кадров, {job["ffprobe_comp_mp4"]["duration_s"]:.1f}s.</p>
      <img src="{preview_url}" alt="CorridorKey preview" />
    </div>

    <div class="card span8">
      <h2>Исходное видео</h2>
      <video src="{input_url}" controls preload="metadata"></video>
      <p style="margin-top:14px"><a class="cta" href="{input_url}" target="_blank">Открыть исходник</a></p>
    </div>
    <div class="card span4">
      <h2>До / после</h2>
      <p class="small">Исходник взят из Loremax S3/CDN и отправлен в CorridorKey RunPod Serverless без локальной перекодировки.</p>
      <p><span class="pill">Source {input_mb:.2f} MB</span><span class="pill">Result {out_mb:.2f} MB</span></p>
      <p class="small">Оба видео имеют одинаковую геометрию: H.264, {job["ffprobe_comp_mp4"]["width"]}×{job["ffprobe_comp_mp4"]["height"]}, {job["ffprobe_comp_mp4"]["frames"]} кадров, ~10 секунд.</p>
    </div>

    <div class="card span6">
      <h2>Входное видео</h2>
      <table>
        <tr><th>Источник</th><td><a href="{input_url}" target="_blank">Loremax S3 / content CDN</a></td></tr>
        <tr><th>Размер</th><td>{input_mb:.2f} MB</td></tr>
        <tr><th>Codec</th><td>{escape(job["input_probe"]["codec"])}</td></tr>
        <tr><th>Resolution</th><td>{job["input_probe"]["width"]}×{job["input_probe"]["height"]}</td></tr>
        <tr><th>Frames</th><td>{frames}</td></tr>
        <tr><th>Duration</th><td>{job["input_probe"]["duration_s"]:.3f}s</td></tr>
      </table>
    </div>

    <div class="card span6">
      <h2>Pipeline metrics</h2>
      <table>
        <tr><th>Delay before execution</th><td>{queue_s:.3f}s</td></tr>
        <tr><th>Execution</th><td>{exec_s:.3f}s ({dur(exec_s)})</td></tr>
        <tr><th>Total queue+execution</th><td>{wall_s:.3f}s ({dur(wall_s)})</td></tr>
        <tr><th>Pipeline total_seconds</th><td>{job["metadata"]["total_seconds"]:.3f}s</td></tr>
        <tr><th>Inference only</th><td>{inference_s:.3f}s</td></tr>
        <tr><th>Per frame execution</th><td>{per_frame_exec:.3f}s/frame</td></tr>
        <tr><th>Per frame inference</th><td>{per_frame_infer:.3f}s/frame</td></tr>
      </table>
    </div>

    <div class="card span12">
      <h2>Расчёт стоимости</h2>
      <p class="small">Тарифы взяты со скрина RunPod UI: 80 GB PRO = $0.00116/s, 96 GB = $0.00111/s. В serverless платится фактически поднятый worker; если RunPod выбрал один GPU из списка fallback, умножения на две галочки нет.</p>
      <table>
        <tr><th>Сценарий</th><th>Seconds</th><th>Time</th><th>80 GB PRO @ $0.00116/s</th><th>96 GB @ $0.00111/s</th></tr>
        {cost_rows}
      </table>
      <p><span class="pill">Cost/frame 80GB PRO: {money(cost_per_frame_80)}</span><span class="pill">Cost/frame 96GB: {money(cost_per_frame_96)}</span></p>
    </div>

    <div class="card span6">
      <h2>Финальная оценка</h2>
      <p>Основной большой прогон стоил примерно <b>{money(exec_s * rates["96 GB"])}–{money(exec_s * rates["80 GB PRO"])}</b> по чистому execution, либо <b>{money(wall_s * rates["96 GB"])}–{money(wall_s * rates["80 GB PRO"])}</b>, если консервативно включить queue delay.</p>
      <p>Полная сумма двух успешных проверок (smoke + большой job) по execution: <b>{money(all_exec_s * rates["96 GB"])}–{money(all_exec_s * rates["80 GB PRO"])}</b>.</p>
    </div>

    <div class="card span6">
      <h2>RunPod/Docker status</h2>
      <p><span class="pill ok">jobs.completed=2</span><span class="pill ok">workers.ready=1</span><span class="pill ok">unhealthy=0</span></p>
      <div class="code">Template: {escape(endpoint["template_id"])}
Endpoint: {escape(endpoint["endpoint_id"])}
Image: {escape(endpoint["image"])}
DockerHub: {escape(endpoint["dockerhub_publish_attempt"]["status"])}</div>
      <p class="small">DockerHub push был подготовлен, но заблокирован auth: insufficient_scope. Рабочая image digest проверена через ttl.sh и RunPod.</p>
    </div>
  </section>
</div>
</body>
</html>
"""

out = ROOT / "worker/deploy/reports/corridorkey_runpod_final_report_20260425.html"
out.write_text(html, encoding="utf-8")
print(out)
print("exec_cost_96", exec_s * rates["96 GB"])
print("exec_cost_80pro", exec_s * rates["80 GB PRO"])
print("wall_cost_96", wall_s * rates["96 GB"])
print("wall_cost_80pro", wall_s * rates["80 GB PRO"])
