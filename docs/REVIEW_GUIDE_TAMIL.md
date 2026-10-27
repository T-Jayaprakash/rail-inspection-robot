# Review-ல எப்படி present பண்றது (Tamil guide)

## Review-க்கு முன்னாடி (laptop setup, 5 நிமிடம்)

```bash
pip install -r requirements.txt
python dashboard/app.py          # browser-ல http://localhost:5000 open பண்ணுங்க
```
Windows-ல `run_dashboard.bat`-ஐ double-click பண்ணாலும் போதும். Internet இல்லாமலே இது ஓடும்.
Backup-க்கு `output/demo_inspection.mp4` video-வை pen drive-லயும் copy பண்ணி வச்சுக்குங்க.

## Present பண்ற வரிசை (10–12 நிமிடம்)

1. **Problem (1 நிமிடம்)**: "இந்தியாவில track inspection இன்னும் manual-ஆ தான் நடக்குது. Trackman நடந்தோ trolley தள்ளியோ போய் கண்ணால பார்க்கிறாங்க. ஒரு shift-க்கு சில km தான் cover ஆகும், சின்ன crack-ஐ ஈஸியா miss பண்ணிடுவாங்க."
2. **Solution (1 நிமிடம்)**: "நாங்க ஒரு சின்ன train / go-kart மாதிரி autonomous robot design பண்ணியிருக்கோம். அது track மேலேயே தானாக ஓடி cameras, sensors வச்சு crack, gauge, obstacle-ஐ கண்டுபிடிச்சு control room-க்கு live-ஆ காட்டும்."
3. **Block diagram (PPT slide 4)**: Raspberry Pi தான் brain (vision + dashboard). ESP32 motor control-ஐயும் safety-ஐயும் பார்த்துக்கும்.
4. **Live demo (4 நிமிடம்)**: dashboard-ல **START AUTO** அழுத்துங்க. அப்புறம் இதையெல்லாம் காட்டுங்க:
   - Crack வரும்போது box + severity label வரும், "LAST DEFECT" photo update ஆகும், map-ல ▲ marker விழும்
   - ~20 m-ல gauge **1698 mm (+22)** சிவப்பா மாறும். இது wide gauge fault
   - Boulder தெரிஞ்சதும் "OBSTACLE AHEAD – SLOWING", 2 m-ல **EMERGENCY STOP**. Obstacle remove ஆனதும் தானாக resume ஆகும்
   - **W / S** key-ஐ hold பண்ணா manual drive. **Report** button அழுத்துனா photo-வோட PDF report வரும்
5. **Algorithm (2 நிமிடம்)**: black-hat filter → shape test (rust கறை round-ஆ இருக்கும், crack நீளமா மெல்லிசா இருக்கும்) → severity.
6. **Results (1 நிமிடம்)**: 7/7 cracks, 0 false alarm, 2/2 gauge faults, gauge error 1 mm-க்கும் கம்மி, 2/2 obstacles stop.
7. **Future scope**: YOLOv8, உள்ளே இருக்கும் flaw-க்கு ultrasonic probe, solar charging.

## Examiner கேட்கக்கூடிய கேள்விகள்

| கேள்வி | பதில் |
|---|---|
| இது real robot-ஆ? | "Software full-ஆ ready. Hardware-ல அதே code-ஐ `--hardware` flag போட்டு ஓட்டலாம். Demo-வுக்கு simulator use பண்ணோம். Simulator camera image-ஐயும் sensor value-ஐயும் மட்டும் தான் கொடுக்கும். Detection எல்லாம் real OpenCV code தான் பண்ணுது. Ground truth வச்சு accuracy-யும் measure பண்ணோம்." |
| Crack எங்க இருக்குன்னு எப்படி தெரியும்? | Wheel encoder distance + image-ல crack இருக்கும் pixel offset × mm/px. கூடவே GPS-ம் record ஆகும். |
| Pi hang ஆனா என்ன ஆகும்? | ESP32-ல 1 s watchdog இருக்கு. Command வரலைன்னா motor நின்னுடும். Ultrasonic hard-stop-ம் E-stop-ம் ESP32-லயே இருக்கு. |
| Train வந்தா? | இந்த robot maintenance block நேரத்துல மட்டும் ஓடும். Track-ல இருந்து எடுக்கக்கூடிய எடை தான் (~15 kg). |
| Internal crack? | Camera surface crack-ஐ மட்டும் தான் பார்க்கும். Internal flaw-க்கு ultrasonic probe சேர்க்கணும் (future scope). |
| Cost? | சுமார் ₹22–25 ஆயிரம். Track recording car-க்கு கோடிக்கணக்குல செலவாகும். |
