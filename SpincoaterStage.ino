 
#include <ODriveUART.h>
#include <SoftwareSerial.h>

// Documentation for this example can be found here:
// https://docs.odriverobotics.com/v/latest/guides/arduino-uart-guide.html


////////////////////////////////
// Set  up serial pins to the ODrive
////////////////////////////////

// Below are some sample configurations.
// You can comment out the default one and uncomment the one you wish to use.
// You can of course use something different if you like
// Don't forget to also connect ODrive ISOVDD and ISOGND to Arduino 3.3V/5V and GND.

// Arduino without spare serial ports (such as Arduino UNO) have to use software serial.
// Note that this is implemented poorly and can lead to wrong data sent or read.
// pin 8: RX - connect to    TX
// pin 9: TX - connect to ODrive RX
// SoftwareSerial odrive_serial(8, 9);
// unsigned long baudrate = 19200; // Must match what you configure on the ODrive (see docs for details)

// Teensy 3 and 4 (all versions) - Serial1
// pin 0: RX - connect to ODrive TX
// pin 1: TX - connect to ODrive RX
// See https://www.pjrc.com/teensy/td_uart.html for other options on Teensy
// HardwareSerial& odrive_serial = Serial1;
// int baudrate = 115200; // Must match what you configure on the ODrive (see docs for details)

// Arduino Mega or Due - Serial1
// pin 19: RX - connect to ODrive TX
// pin 18: TX - connect to ODrive RX
// See https://www.arduino.cc/reference/en/language/functions/communication/serial/ for other options
HardwareSerial& odrive_serial = Serial1;
unsigned long baudrate = 115200; // Must match what you configure on the ODrive (see docs for details)


ODriveUART odrive(odrive_serial);

bool enabled = false;

int RPM = 5000;

void MS() {
  const unsigned long sampleInterval = 100;     // ms
  const unsigned long duration        = 30000;  // 30 sec

  const int maxSamples = duration / sampleInterval; // = 300 samples
  float samples[maxSamples];
  int sampleCount = 0;

  unsigned long startTime = millis();
  unsigned long lastSample = 0;

  Serial.println("Starting speed measurement...");

  while (millis() - startTime < duration) {
    unsigned long now = millis();

    if (now - lastSample >= sampleInterval) {
      lastSample = now;

      // Read velocity (rps) and convert to RPM
      float rps = odrive.getVelocity();
      float rpm = rps * 60.0f;

      if (sampleCount < maxSamples) {
        samples[sampleCount++] = rpm;
      }
    }
  }

  Serial.println("Speed measurement complete!");

  // ---- Calculate average ----
  float sum = 0.0f;
  for (int i = 0; i < sampleCount; i++) {
    sum += samples[i];
  }
  float avg = sum / sampleCount;

  // ---- Calculate standard deviation ----
  float var = 0.0f;
  for (int i = 0; i < sampleCount; i++) {
    float diff = samples[i] - avg;
    var += diff * diff;
  }
  var /= sampleCount;              // population variance
  float stddev = sqrt(var);        // standard deviation

  // ---- Print results ----
  Serial.print("Average Speed (RPM): ");
  Serial.println(avg, 3);          // 3 decimal places

  Serial.print("Std Dev (RPM): ");
  Serial.println(stddev, 3);
}
void setup() 
{
  Serial.flush();

  odrive_serial.begin(baudrate);

  Serial.begin(115200); // Serial to PC
}

void loop() 
{
  if (!enabled) {
    // Listen for the start command
    if (Serial.available()) {
      String cmd = Serial.readStringUntil('\n');
      cmd.trim();
      if (cmd == "START") {
        enabled = true;
        Serial.println("Enabled!");
      }
    }
    return; // Skip sending anything until enabled
  }
  
  delay(10);

  Serial.println("Waiting for ODrive...");
  while (odrive.getState() == AXIS_STATE_UNDEFINED) {
    delay(100);
  }

  Serial.println("found ODrive");
     
  Serial.print("DC voltage: ");
  Serial.println(odrive.getParameterAsFloat("vbus_voltage"));

  Serial.println("Enabling closed loop control...");
  while (odrive.getState() != AXIS_STATE_CLOSED_LOOP_CONTROL) {
    odrive.clearErrors();
    odrive.setState(AXIS_STATE_CLOSED_LOOP_CONTROL);

    delay(100);

    if (odrive.getState() == AXIS_STATE_IDLE)
      {
        odrive.setState(AXIS_STATE_FULL_CALIBRATION_SEQUENCE);

        while (odrive.getState() != AXIS_STATE_IDLE)
        {
          delay(100);
        }
      }
  }

  odrive_serial.print("w axis0.controller.config.vel_ramp_rate ");
  odrive_serial.println(15);
  odrive_serial.flush();

  delay(10);

  Serial.println("Spinning");

  odrive.setVelocity(float((RPM + 10)/60));

  while (odrive.getVelocity() < (RPM)/60*0.98)
  {
    delay(20);
  }

  MS();

  Serial.println("Stopping");

  odrive_serial.print("w axis0.controller.config.vel_ramp_rate ");
  odrive_serial.println(100);
  odrive_serial.flush();

  odrive.setVelocity(0);

  while (odrive.getVelocity() > 0.1)
  {
    delay(100);
  }

  delay(1000);

  odrive_serial.print("w axis0.controller.config.vel_ramp_rate ");
  odrive_serial.println(15);
  odrive_serial.flush();

  Serial.println("Homing Motor");

  odrive.setState(AXIS_STATE_ENCODER_INDEX_SEARCH);

  delay(100);

  enabled = false;
  
}
