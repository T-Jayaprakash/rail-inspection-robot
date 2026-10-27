/*
 * Rail Track Inspection Robot - ESP32 low-level controller
 * ---------------------------------------------------------
 * Jobs of this board:
 *   - drive the two DC geared motors (BTS7960 / L298N) with closed-loop speed control
 *   - count wheel-encoder pulses -> distance travelled (chainage)
 *   - read front & rear ultrasonic sensors (HC-SR04) -> HARD safety stop
 *   - read IR sensors over each rail head (TCRT5000) -> rail break / missing rail
 *   - read MPU6050 -> vibration (g RMS) and tilt
 *   - read battery voltage, E-stop button, drive buzzer + paint-marker relay
 *   - talk to the Raspberry Pi over USB serial (115200, one JSON per line)
 *
 * Pi  -> ESP32 :  {"cmd":"drive","v":1.20}   speed in m/s (negative = reverse)
 *                 {"cmd":"stop"}  {"cmd":"mark"}  {"cmd":"reset_enc"}
 * ESP32 -> Pi  :  {"enc":12.345,"spd":0.98,"us":3.10,"usr":4.00,"bat":11.9,
 *                  "vib":0.06,"tmp":38.5,"tilt":0.2,"irL":1,"irR":1,"estop":0}
 *
 * Safety: the robot stops by itself (even if the Pi crashes) when
 *   - an obstacle is closer than STOP_CM in the direction of travel
 *   - no command arrives from the Pi for WATCHDOG_MS
 *   - the E-stop button is pressed
 *
 * Libraries: none required except Wire (built-in).  Board: "ESP32 Dev Module".
 */
#include <Wire.h>

// ------------------------------------------------------------------ pins
#define M_L_PWM   25      // motor driver (BTS7960: RPWM / LPWM)
#define M_R_PWM   26
#define M_EN      27
#define ENC_A     34      // wheel encoder channel A (interrupt)
#define ENC_B     35
#define US_F_TRIG 5       // front HC-SR04
#define US_F_ECHO 18
#define US_R_TRIG 19      // rear HC-SR04
#define US_R_ECHO 23
#define IR_LEFT   32      // TCRT5000 over left rail head (LOW = rail present)
#define IR_RIGHT  33
#define BAT_ADC   36      // battery through 100k/22k divider
#define ESTOP_PIN 4       // NC mushroom button to GND
#define BUZZER    2
#define MARKER    15      // relay -> paint-spray solenoid
#define LED_OK    13

// -------------------------------------------------------------- constants
const float WHEEL_DIA_M     = 0.10;     // 100 mm flanged wheel
const int   PULSES_PER_REV  = 600;      // encoder PPR x gear ratio (calibrate!)
const float M_PER_PULSE     = 3.14159f * WHEEL_DIA_M / PULSES_PER_REV;
const float MAX_SPEED       = 1.5;      // m/s
const int   STOP_CM         = 150;      // hard stop distance
const int   SLOW_CM         = 300;
const unsigned long WATCHDOG_MS = 1000;
const float KP = 180.0, KI = 90.0;      // speed PI gains (PWM per m/s)

// --------------------------------------------------------------- state
volatile long encCount = 0;
float targetV = 0, measV = 0, integ = 0;
long lastCount = 0;
unsigned long lastCmdMs = 0, lastCtrlMs = 0, lastTxMs = 0, markUntil = 0;
float usFront = 4.0, usRear = 4.0, vibG = 0, tiltDeg = 0, tempC = 0;
String rx;

const int MPU = 0x68;

void IRAM_ATTR encISR() {
  if (digitalRead(ENC_B)) encCount++; else encCount--;
}

// ---------------------------------------------------------------- setup
void setup() {
  Serial.begin(115200);
  pinMode(M_EN, OUTPUT);
  ledcAttach(M_L_PWM, 20000, 8);      // ESP32 core 3.x API
  ledcAttach(M_R_PWM, 20000, 8);
  pinMode(ENC_A, INPUT); pinMode(ENC_B, INPUT);
  attachInterrupt(digitalPinToInterrupt(ENC_A), encISR, RISING);
  pinMode(US_F_TRIG, OUTPUT); pinMode(US_F_ECHO, INPUT);
  pinMode(US_R_TRIG, OUTPUT); pinMode(US_R_ECHO, INPUT);
  pinMode(IR_LEFT, INPUT); pinMode(IR_RIGHT, INPUT);
  pinMode(ESTOP_PIN, INPUT_PULLUP);
  pinMode(BUZZER, OUTPUT); pinMode(MARKER, OUTPUT); pinMode(LED_OK, OUTPUT);
  digitalWrite(M_EN, HIGH);

  Wire.begin(21, 22);
  Wire.beginTransmission(MPU); Wire.write(0x6B); Wire.write(0); Wire.endTransmission();   // wake
  Wire.beginTransmission(MPU); Wire.write(0x1C); Wire.write(0x08); Wire.endTransmission(); // +-4 g
  beep(2);
}

// --------------------------------------------------------------- helpers
void beep(int n) {
  for (int i = 0; i < n; i++) { digitalWrite(BUZZER, HIGH); delay(60); digitalWrite(BUZZER, LOW); delay(60); }
}

float readUltrasonicM(int trig, int echo) {
  digitalWrite(trig, LOW); delayMicroseconds(2);
  digitalWrite(trig, HIGH); delayMicroseconds(10);
  digitalWrite(trig, LOW);
  unsigned long us = pulseIn(echo, HIGH, 25000);      // ~4.3 m timeout
  if (us == 0) return 4.0;
  return us * 0.000343f / 2.0f;
}

void readIMU() {
  Wire.beginTransmission(MPU); Wire.write(0x3B); Wire.endTransmission(false);
  Wire.requestFrom(MPU, 8, true);
  int16_t ax = Wire.read() << 8 | Wire.read();
  int16_t ay = Wire.read() << 8 | Wire.read();
  int16_t az = Wire.read() << 8 | Wire.read();
  int16_t t  = Wire.read() << 8 | Wire.read();
  float gx = ax / 8192.0, gy = ay / 8192.0, gz = az / 8192.0;
  // vibration = deviation of |a| from 1 g, smoothed (RMS-like)
  float mag = sqrt(gx * gx + gy * gy + gz * gz);
  float dev = fabs(mag - 1.0);
  vibG = 0.9 * vibG + 0.1 * dev;
  tiltDeg = atan2(gy, gz) * 57.2958;   // cross-level (cant) indication
  tempC = t / 340.0 + 36.53;
}

void setMotor(int pwm) {   // -255 .. 255
  pwm = constrain(pwm, -255, 255);
  if (pwm >= 0) { ledcWrite(M_L_PWM, pwm); ledcWrite(M_R_PWM, 0); }
  else          { ledcWrite(M_L_PWM, 0);   ledcWrite(M_R_PWM, -pwm); }
}

float numAfter(const String &s, const char *key) {
  int i = s.indexOf(key);
  if (i < 0) return 0;
  i = s.indexOf(':', i) + 1;
  return s.substring(i).toFloat();
}

void handleCommand(const String &s) {
  lastCmdMs = millis();
  if (s.indexOf("\"drive\"") >= 0) {
    targetV = constrain(numAfter(s, "\"v\""), -MAX_SPEED, MAX_SPEED);
  } else if (s.indexOf("\"stop\"") >= 0) {
    targetV = 0;
  } else if (s.indexOf("\"mark\"") >= 0) {
    digitalWrite(MARKER, HIGH); markUntil = millis() + 300; beep(1);
  } else if (s.indexOf("\"reset_enc\"") >= 0) {
    noInterrupts(); encCount = 0; interrupts(); lastCount = 0;
  }
}

// ----------------------------------------------------------------- loop
void loop() {
  // 1. serial commands from the Raspberry Pi
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') { handleCommand(rx); rx = ""; }
    else if (rx.length() < 120) rx += c;
  }

  unsigned long now = millis();

  // 2. control loop @ 50 Hz
  if (now - lastCtrlMs >= 20) {
    float dt = (now - lastCtrlMs) / 1000.0;
    lastCtrlMs = now;

    noInterrupts(); long cnt = encCount; interrupts();
    measV = 0.7 * measV + 0.3 * ((cnt - lastCount) * M_PER_PULSE / dt);
    lastCount = cnt;

    usFront = readUltrasonicM(US_F_TRIG, US_F_ECHO);
    usRear  = readUltrasonicM(US_R_TRIG, US_R_ECHO);
    readIMU();

    bool estop   = digitalRead(ESTOP_PIN) == HIGH;          // NC button opened
    bool timeout = now - lastCmdMs > WATCHDOG_MS;
    bool blockF  = targetV > 0 && usFront * 100 < STOP_CM;
    bool blockR  = targetV < 0 && usRear  * 100 < STOP_CM;

    float v = targetV;
    if (targetV > 0 && usFront * 100 < SLOW_CM) v = min(v, 0.4f);   // local slow zone
    if (estop || timeout || blockF || blockR) v = 0;

    if (v == 0 && fabs(measV) < 0.05) { integ = 0; setMotor(0); }
    else {
      float err = v - measV;
      integ = constrain(integ + err * dt, -1.5, 1.5);
      float ff = v / MAX_SPEED * 200.0;                 // feed-forward
      setMotor((int)(ff + KP * err + KI * integ));
    }
    digitalWrite(BUZZER, (blockF || blockR || estop) && (now / 250) % 2);
    digitalWrite(LED_OK, !timeout && !estop);
    if (markUntil && now > markUntil) { digitalWrite(MARKER, LOW); markUntil = 0; }
  }

  // 3. telemetry @ 20 Hz
  if (now - lastTxMs >= 50) {
    lastTxMs = now;
    noInterrupts(); long cnt = encCount; interrupts();
    float bat = analogRead(BAT_ADC) / 4095.0 * 3.3 * (122.0 / 22.0);
    Serial.printf("{\"enc\":%.3f,\"spd\":%.2f,\"us\":%.2f,\"usr\":%.2f,\"bat\":%.2f,"
                  "\"vib\":%.3f,\"tmp\":%.1f,\"tilt\":%.2f,\"irL\":%d,\"irR\":%d,\"estop\":%d}\n",
                  cnt * M_PER_PULSE, measV, usFront, usRear, bat, vibG, tempC, tiltDeg,
                  digitalRead(IR_LEFT) == LOW, digitalRead(IR_RIGHT) == LOW,
                  digitalRead(ESTOP_PIN) == HIGH);
  }
}
