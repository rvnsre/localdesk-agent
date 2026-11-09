"""Render reproducible SVG and PNG README artwork from the same scene graph."""
from pathlib import Path
from html import escape
import json
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets"
OUT.mkdir(parents=True, exist_ok=True)
BG, PANEL, BORDER, WHITE, MUTED, BLUE, GREEN = "#0b1020", "#131d32", "#253858", "#edf4ff", "#9eafca", "#68b9ff", "#78e0b5"


class Scene:
    def __init__(self, name, height=580):
        self.name, self.h = name, height
        self.image = Image.new("RGB", (1400, height), BG)
        self.draw = ImageDraw.Draw(self.image)
        self.svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="{height}" viewBox="0 0 1400 {height}">', f'<rect width="1400" height="{height}" fill="{BG}"/>']
        self.rect(20, 20, 1360, height-40, BG, BORDER)

    def rect(self, x, y, w, h, fill=PANEL, outline=BORDER):
        self.draw.rounded_rectangle((x,y,x+w,y+h), radius=18, fill=fill, outline=outline, width=2)
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="{fill}" stroke="{outline}" stroke-width="2"/>')

    def text(self, x, y, value, size=25, color=WHITE, mono=False):
        candidates = [Path("C:/Windows/Fonts/consola.ttf") if mono else Path("C:/Windows/Fonts/segoeui.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
        path = next((p for p in candidates if p.exists()), None)
        font = ImageFont.truetype(str(path), size) if path else ImageFont.load_default()
        self.draw.text((x,y), value, font=font, fill=color)
        family = "Consolas,monospace" if mono else "Segoe UI,DejaVu Sans,sans-serif"
        self.svg.append(f'<text x="{x}" y="{y+size}" font-family="{family}" font-size="{size}" fill="{color}">{escape(value)}</text>')

    def title(self, number, title, subtitle):
        self.text(60,48,number,19,GREEN)
        self.text(60,90,title,46)
        self.text(60,155,subtitle,23,MUTED)

    def save(self):
        self.svg.append("</svg>")
        (OUT/f"{self.name}.svg").write_text("\n".join(self.svg), encoding="utf-8")
        self.image.save(OUT/f"{self.name}.png", optimize=True)


s=Scene("01-hero")
s.text(65,65,"LOCAL VISION  /  DELIBERATE ACTION",22,GREEN)
s.text(65,130,"LocalDesk Agent",76)
s.text(68,240,"Your desktop. Your model. Your approval.",32,MUTED)
s.text(68,300,"A terminal-first automation engine for Windows, macOS and Linux.",25,MUTED)
for x,title,sub in [(65,"LOCAL INFERENCE","Vision through your local API"),(495,"MEASURED PERFORMANCE","Capture, model and action timings"),(925,"CONTROLLED INPUT","Validated plans and fail-safe stop")]:
    s.rect(x,390,405,125)
    s.text(x+22,411,title,20,BLUE)
    s.text(x+22,458,sub,20)
s.save()

s=Scene("02-workflow",500)
s.title("01 / THE EXECUTION LOOP","See. Plan. Validate. Act.","Every desktop action passes through explicit boundaries.")
for i,(title,sub) in enumerate([("Capture","Fresh screenshot"),("Model","Local vision API"),("Validate","Bounds and limits"),("Approve","Review the plan"),("Execute","Sequential input")]):
    x=60+i*260
    s.rect(x,245,240,125)
    s.text(x+20,260,f"0{i+1}",20,GREEN)
    s.text(x+20,291,title,28)
    s.text(x+20,335,sub,17,MUTED)
s.text(60,415,"Freshness check before execution  /  No parallel mouse or keyboard actions",23,BLUE)
s.save()

s=Scene("03-platforms",610)
s.title("02 / PLATFORM ADAPTERS","One interface. Native capture paths.","Automatic calibration selects the fastest available capture backend on your device.")
for x,title,lines in [(60,"Windows",["DXcam / Desktop Duplication","MSS / ImageGrab fallback","Active desktop access required"]),(500,"macOS",["MSS / ImageGrab fallback","Accessibility permissions","Screen Recording permissions"]),(940,"Linux",["MSS / ImageGrab fallback","X11 preferred","Wayland restrictions vary"] )]:
    s.rect(x,240,400,265)
    s.text(x+25,265,title,34,BLUE)
    for i,line in enumerate(lines): s.text(x+25,335+i*45,line,19,MUTED)
s.text(60,540,"PyAutoGUI input  +  clipboard text  +  shared validation policy",23,GREEN)
s.save()

s=Scene("04-performance",650)
s.title("03 / PERFORMANCE EVIDENCE","Measured, never assumed.","Local capture timings are separate from real model and task completion time.")
path=ROOT/"docs/benchmarks/capture-windows.json"
report=json.loads(path.read_text()) if path.exists() else {}
results=report.get("results",{})
for i,name in enumerate(["legacy","optimized"]):
    result=results.get(name,{})
    value=result.get("median_ms")
    s.rect(60,235+i*125,815,105)
    s.text(85,250+i*125,"Original capture path" if name=="legacy" else "Calibrated OpenCV path",25,BLUE)
    label=f"{value:.2f} ms median  |  {result.get('p95_ms',0):.2f} ms p95" if value is not None else "Measurement unavailable on this host"
    s.text(85,290+i*125,label,23)
s.rect(920,235,420,230)
s.text(945,260,"END-TO-END TARGET",21,GREEN)
s.text(945,305,"2x faster",43)
s.text(945,372,"Not verified: local model API",19,MUTED)
s.text(945,405,"was unavailable during testing.",19,MUTED)
s.text(60,530,f"Capture benchmark: {report.get('iterations',0)} samples after {report.get('warmups',0)} warmups / Windows",22,MUTED)
s.text(60,575,"Raw timings and methodology: docs/benchmarks/  |  No model-speed claim",22,MUTED)
s.save()

s=Scene("05-terminal",620)
s.title("04 / TERMINAL EXPERIENCE","Readable plans. Explicit approval.","Illustrative demo — this panel is a product mockup, not a captured benchmark.")
s.rect(60,230,1280,320,"#080e19")
lines=[("$ localdesk --profile balanced \"Find the search field\"",BLUE),("Plan: Focus the visible search field.",WHITE),("  1. click left (640, 310)",MUTED),("Execute this plan? [y/N] y",GREEN),("Freshness check passed. Executing 1 validated action.",MUTED),("$ localdesk doctor --json",BLUE),("$ localdesk benchmark --mode capture --output capture.json",BLUE)]
for i,(line,color) in enumerate(lines): s.text(88,250+i*39,line,22,color,True)
s.save()
