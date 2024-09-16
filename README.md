# Meshtastic Antenna Tester

The **Meshtastic Antenna Tester** is a tool designed to compare the performance of different antennas **and locations** using Meshtastic devices. It measures and analyzes signal strength (RSSI) and signal-to-noise ratio (SNR) to help you identify the best antenna and optimal locations for specific conditions. This tool uses a portable test node (TCP client, Heltec v3 is recommended) to gather data at different locations and a fixed destination node for consistent measurements.

## Overview

The Meshtastic Antenna Tester allows you to:

- Compare antenna performance under identical conditions.
- Evaluate the suitability of different locations for communication.
- Analyze signal strength (RSSI) and signal-to-noise ratio (SNR).
- Manage and export test data for further analysis.

## Permissions on Android

This app requires permission to access the **Download** folder to import and export database files. When you first open the app, you may be prompted to grant this permission. If you deny the permission, you can grant it later by going to your device's app settings. Please grant the necessary permissions to ensure the app functions correctly.

## Important Notice for TCP/BLE Connections

Please make sure that the node you are connecting to (BLE/TCP) is **not already connected to any other device**. A Meshtastic node can only maintain one active connection at a time. If the node is already in use, the connection attempt will fail without proper error messages and error handling. In such a case, restart the app and reconnect.

## Tabs and Their Functions

### Test Tab

This tab is the core of the application where tests are conducted. You connect to a Meshtastic device (the portable test node) using TCP. Messages are sent to a fixed destination node, which should always remain in the same location with the same antenna setup to ensure consistent results. The number of messages sent is displayed in real-time. A countdown timer shows when the next message will be sent. Acknowledgments (ACKs) are not displayed in real-time but are checked periodically. The number of ACKs received is updated after each interval, and the connection status is visualized with an icon (green = connected, red = no connection).

### Setup Tab

In this tab, you configure the settings for your test. You need to input the **Antenna Name**, **Buy URL**, **Notes**, **Location**, and select the **Connection Type**. If you're using a TCP connection, provide the IP address of your portable test node. The **Destination Node ID** is critical and should always refer to the fixed, stationary node with a constant antenna setup. Changing the setup of this node requires deleting the database and starting fresh.

### Antennas Tab

This tab displays and sorts the results of tested antennas. You can sort by antenna name, average RSSI, or calculated score. Clicking on a row reveals additional information like shop links and notes. The score is based on RSSI values, allowing for easy comparison of antenna performance at specific locations.

### Locations Tab

In this tab, you can view results for different locations. Similar to the Antennas tab, locations can be sorted by name, average SNR, or calculated score. The best-performing antenna for each location is highlighted based on test results, making it easier to select the optimal setup for each environment.

### Data Tab

This tab allows you to manage your data by deleting specific antennas or locations, or even the entire database. You can also export test results as a CSV file or the entire database for further analysis in other programs.

### Guide Tab

This tab provides a detailed guide on how to use the app, including the purpose of each tab and instructions for setting up your tests.

## Importing a Database on Android

On Android devices, the file picker is not available. To import a database, place the `.db` file in the `Download` folder of your device. Then, go to the **Data** tab in the app and tap **Import DB**. You will see a list of available `.db` files to select from.

## Exporting Data

When exporting data, the exported CSV or database file is saved to the `Documents` folder on Windows or the `Download` folder on Android. On Windows, after exporting, you can open the file or folder directly by clicking **Open** in the Snackbar. On Android, you will receive a confirmation message, and you can access the exported files using a file manager app.

## Technical Explanations

### RSSI (Received Signal Strength Indicator)

RSSI indicates the strength of the received signal in dBm. A higher value (closer to 0) means a stronger signal quality. Typical values range from -120 dBm (very weak) to 0 dBm (very strong). RSSI is used to evaluate the quality of the connection between two Meshtastic devices.

### SNR (Signal-to-Noise Ratio)

SNR measures the ratio between the received signal and background noise, expressed in decibels (dB). A higher value indicates better signal quality. Negative SNR values mean that the noise is stronger than the signal, indicating a poor connection. SNR is particularly useful for evaluating environmental conditions at a location.

### Destination Node ID

The Destination Node ID is the unique identifier of the fixed, stationary Meshtastic device to which all test messages are sent. This node should remain in a consistent setup (same location, same antenna) to ensure reliable and comparable results. If the setup of this node changes, you must delete the database and start fresh with new tests.

## Scores and Their Calculation

### Antenna Score

The Antenna Score is calculated on a scale of 1 to 10 based on the average RSSI value for a specific antenna at a specific location. The score allows for the comparison of antenna performance under identical conditions. The score is determined by comparing the average RSSI of the antenna against the minimum and maximum RSSI values recorded for that location.

### Location Score

The Location Score is also calculated on a scale of 1 to 10, but it is based on the average SNR value for a location. This score helps evaluate the suitability of a location for communication, taking into account environmental factors like noise. Scores are calculated by comparing the average SNR of the location with the minimum and maximum SNR values across all tested locations.

## Note

This app was developed by **OE3JGW / Jürgen Waissnix**. If you want to support me, you can do so via PayPal at **waissnix@gmail.com**. You can also use this email address for support inquiries for this app.

---

*For more information, please refer to the in-app guide or contact the developer.*
