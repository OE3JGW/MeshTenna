import flet as ft
import meshtastic
import meshtastic.tcp_interface
import meshtastic.ble_interface
import sqlite3
import time
import os
import platform
from pubsub import pub
from datetime import datetime
import queue
import webbrowser


def check_android_permissions(page):
    if platform.system() == "Linux" and "ANDROID_STORAGE" in os.environ:
        download_path = "/storage/emulated/0/Download"
        if not os.access(download_path, os.R_OK):
            # Permission is not granted
            show_permission_dialog(page)



def show_permission_dialog(page):
    def close_dialog(e):
        # Only closes the dialog
        permission_dialog.open = False
        page.update()

    permission_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Permission Required"),
        content=ft.Text(
            "This app requires permission to access the Download folder to import and export files. "
            "Please grant the necessary permissions in the android app permission settings."
        ),
        actions=[
            ft.TextButton("OK", on_click=close_dialog)
        ],
        on_dismiss=lambda e: permission_dialog.close(),
    )
    page.dialog = permission_dialog
    permission_dialog.open = True
    page.update()






# Global variables for database paths
DATABASE_FILENAME = "antenna_tester.db"
CSV_FILENAME = "exported_results"

# Set the correct path for DATABASE_FILEPATH
if platform.system() == "Linux" and "ANDROID_STORAGE" in os.environ:
    DATABASE_PATH = "/data/data/com.flet.meshtenna/files"
    CSV_EXPORT_PATH = "/storage/emulated/0/Download"
else:
    DATABASE_PATH = os.path.expanduser("~/Documents")
    CSV_EXPORT_PATH = DATABASE_PATH


# Create directory if it does not exist
if not os.path.exists(DATABASE_PATH):
    os.makedirs(DATABASE_PATH)


timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
DATABASE_FILEPATH = os.path.join(DATABASE_PATH, DATABASE_FILENAME)
EXPORT_CSV_FILE = os.path.join(CSV_EXPORT_PATH, f"{CSV_FILENAME}_{timestamp}.csv")

#EXPORT_CSV_FILE = os.path.join("/storage/emulated/0/Download", "exported_results.csv")


# Queue for database queries
db_queue = queue.Queue()
is_db_processing = False

# Handles all database accesses of any kind
def database_manager(query, params=(), fetchone=False, fetchall=False, commit=False):
    global is_db_processing
    result = None

    # Insert request into the queue
    db_queue.put((query, params, fetchone, fetchall, commit))

    # If no processing is currently running, start it
    if not is_db_processing:
        result = process_db_queue()

    return result

def process_db_queue():
    global is_db_processing
    result = None

    if not db_queue.empty():
        is_db_processing = True
        # Get next request from the queue
        query, params, fetchone, fetchall, commit = db_queue.get()

        # Performs the actual database operation
        conn = sqlite3.connect(DATABASE_FILEPATH, check_same_thread=False)
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            if fetchone:
                result = cursor.fetchone()
            if fetchall:
                result = cursor.fetchall()
            if commit:
                conn.commit()
        except Exception as e:
            print(f"Database error: {e}")
            result = []
        finally:
            cursor.close()
            conn.close()

        # Process the next request
        is_db_processing = False
        process_db_queue()  # Repeat until the queue is empty

    return result if result is not None else []

def initialize_database(page):
    # Check if the database already exists
    db_exists = os.path.exists(DATABASE_FILEPATH)

    query = '''
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            antenna_name TEXT,
            url TEXT,
            notes TEXT,
            location TEXT,
            node_name TEXT,
            node_id TEXT,
            connection_type TEXT,
            address TEXT,
            timestamp TEXT,
            rssi INTEGER,
            snr REAL
        )
    '''
    database_manager(query, commit=True)

    # After the query, check again if the database now exists
    if os.path.exists(DATABASE_FILEPATH) and not db_exists:
        page.overlay.append(ft.SnackBar(ft.Text("Database created successfully!"), open=True))
    elif db_exists:
        page.overlay.append(ft.SnackBar(ft.Text("Database already exists."), open=True))
    else:
        page.overlay.append(ft.SnackBar(ft.Text("Failed to create the database."), open=True))
    page.update()










# Global variables for storing sent message ID and test start time
sent_message_id = None
test_start_time = None
test_running = False
settings_saved = False  # This variable checks if the settings have been saved
stop_sending = False

# Global variables for message and ACK count
messages_sent = 0
acks_received = 0
ack_queue = queue.Queue()  # Queue for processing ACKs
















def on_setting_change(e):
    global settings_saved
    settings_saved = False




def get_min_rssi(antenna_name=None, location=None):
    query = "SELECT MIN(rssi) FROM results WHERE 1=1"
    params = []
    
    if antenna_name:
        query += " AND antenna_name = ?"
        params.append(antenna_name)
    
    if location and location != "All Locations":
        query += " AND location = ?"
        params.append(location)
    
    result = database_manager(query, params, fetchone=True)
    return result[0] if result and result[0] is not None else -120

def get_max_rssi(antenna_name=None, location=None):
    query = "SELECT MAX(rssi) FROM results WHERE 1=1"
    params = []
    
    if antenna_name:
        query += " AND antenna_name = ?"
        params.append(antenna_name)
    
    if location and location != "All Locations":
        query += " AND location = ?"
        params.append(location)
    
    result = database_manager(query, params, fetchone=True)
    return result[0] if result and result[0] is not None else 0


def get_min_snr(location=None):
    query = "SELECT MIN(snr) FROM results WHERE 1=1"
    params = []
    
    if location and location != "All Locations":
        query += " AND location = ?"
        params.append(location)
    
    result = database_manager(query, params, fetchone=True)
    return result[0] if result and result[0] is not None else -100


def get_max_snr(location=None):
    query = "SELECT MAX(snr) FROM results WHERE 1=1"
    params = []
    
    if location and location != "All Locations":
        query += " AND location = ?"
        params.append(location)
    
    result = database_manager(query, params, fetchone=True)
    return result[0] if result and result[0] is not None else 100


def calculate_avg_rssi(antenna_name=None, location=None):
    query = "SELECT rssi FROM results WHERE 1=1"
    params = []
    
    if antenna_name:
        query += " AND antenna_name = ?"
        params.append(antenna_name)
    
    if location and location != "All Locations":
        query += " AND location = ?"
        params.append(location)
    
    rssi_values = [row[0] for row in database_manager(query, params, fetchall=True)]
    
    if not rssi_values:
        #print(f"No RSSI values found for antenna {antenna_name} at location {location}")
        return 0
    
    avg_rssi = sum(rssi_values) / len(rssi_values)
    #print(f"Avg RSSI for antenna {antenna_name} at location {location}: {avg_rssi}")
    return avg_rssi




def calculate_avg_snr(location=None):
    query = "SELECT snr FROM results WHERE location = ?"
    params = [location]
    
    snr_values = [row[0] for row in database_manager(query, params, fetchall=True)]
    
    if not snr_values:
        return 0
    
    avg_snr = sum(snr_values) / len(snr_values)
    return avg_snr




def calculate_rssi_score(antenna_name=None, location=None):
    avg_rssi = calculate_avg_rssi(antenna_name=antenna_name, location=location)
    min_rssi = get_min_rssi(location=location)
    max_rssi = get_max_rssi(location=location)

    if max_rssi == min_rssi:
        return 5.0

    score = (avg_rssi - min_rssi) / (max_rssi - min_rssi) * 9 + 1
    return max(1.0, min(10.0, round(score, 1)))


def calculate_snr_score(location=None):
    avg_snr = calculate_avg_snr(location=location)
    
    result = database_manager("SELECT MIN(snr), MAX(snr) FROM results", fetchone=True)
    global_min_snr, global_max_snr = result
    
    if global_max_snr == global_min_snr:
        return 5.0

    score = (avg_snr - global_min_snr) / (global_max_snr - global_min_snr) * 9 + 1
    return max(1.0, min(10.0, round(score, 1)))



expanded_row = None
expanded_row_text_elements = []

def toggle_row(additional_info_row, text_elements, page):
    #print(f"Toggling row for antenna: {text_elements[0].value}")
    global expanded_row, expanded_row_text_elements

    # Close previous row
    if expanded_row and expanded_row != additional_info_row:
        expanded_row.visible = False
        for text in expanded_row_text_elements:
            text.weight = "normal"
        expanded_row = None

    # Toggle visibility of current row
    is_expanded = not additional_info_row.visible
    additional_info_row.visible = is_expanded

    # Set the font to bold when the row is visible
    for text in text_elements:
        text.weight = "bold" if is_expanded else "normal"

    if is_expanded:
        expanded_row = additional_info_row
        expanded_row_text_elements = text_elements
    else:
        expanded_row = None
        expanded_row_text_elements = []

    #print(f"Row visibility: {additional_info_row.visible}")  # Sichtbarkeit überprüfen

    page.update()








def main(page: ft.Page):
    check_android_permissions(page)
    global interface, stop_sending, connection_status_icon, connection_status_text, test_start_time, sort_column, sort_descending, min_snr, max_snr, min_rssi, max_rssi
    interface = None
    sort_column = "score"  # Sort by "score" by default
    sort_descending = True  # Sort in descending order by default

    # Function to update the GUI for sent messages and ACKs
    def update_message_ack_display():
        messages_sent_value.value = f"{messages_sent}"
        acks_received_value.value = f"{acks_received}"
        page.update()

    try:
        # Initialize the database (creates the table if necessary)
        initialize_database(page)

        # Execute the SQL queries to fetch MIN/MAX SNR and RSSI
        result = database_manager("SELECT MIN(snr), MAX(snr) FROM results", fetchone=True)
        min_snr, max_snr = result if result else (None, None)

        result = database_manager("SELECT MIN(rssi), MAX(rssi) FROM results", fetchone=True)
        min_rssi, max_rssi = result if result else (None, None)

    except Exception as e:
        print(f"Database operation error: {e}")
        error_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Database Error"),
            content=ft.Text(f"An error occurred while accessing the database: {str(e)}"),
            actions=[],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        page.overlay.append(error_dialog)
        error_dialog.open = True
        page.update()

    finally:
        # Since no manual `conn` and `cursor` connection is used anymore, no closing is necessary.
        pass






    def on_connection_type_change(e):
        tcp_ip_input.visible = connection_type_dropdown.value == "TCP"
        ble_device_input.visible = connection_type_dropdown.value == "BLE"
        page.update()

    def on_visible_message_change(e):
        message_text_input.visible = visible_message_checkbox.value
        page.update()




    def load_results(location_filter=None):
        # Ensure that the database exists
        if not os.path.exists(DATABASE_FILEPATH):
            page.overlay.append(ft.SnackBar(ft.Text("No database connection."), open=True))
            return

        # Load distinct locations from the database
        location_query = "SELECT DISTINCT location FROM results"
        locations = ["All Locations"] + [row[0] for row in database_manager(location_query, fetchall=True)]
        location_filter_dropdown.options = [ft.dropdown.Option(loc) for loc in locations]

        # Set default value for location_filter
        if not location_filter_dropdown.value:
            location_filter_dropdown.value = "All Locations"

        location_filter = location_filter_dropdown.value

        rows = []

        # Create the data query based on the location_filter
        if location_filter == "All Locations" or location_filter is None:
            query = '''SELECT id, antenna_name, location, url, notes FROM results GROUP BY antenna_name, location, url, notes'''
            params = ()
        else:
            query = '''SELECT id, antenna_name, location, url, notes FROM results WHERE location = ? GROUP BY antenna_name, location, url, notes'''
            params = (location_filter,)

        # Retrieve results from the database
        results = database_manager(query, params, fetchall=True)

        # Calculate avg_rssi and score for each antenna, based on the selected location
        for result_row in results:
            avg_rssi = calculate_avg_rssi(antenna_name=result_row[1], location=location_filter)
            score = calculate_rssi_score(antenna_name=result_row[1], location=location_filter)
            rows.append((result_row[0], result_row[1], avg_rssi, score, result_row[3], result_row[4]))

        # Sort according to the selected criterion
        if sort_column == "antenna_name":
            rows = sorted(rows, key=lambda x: x[1], reverse=sort_descending)
        elif sort_column == "rssi":
            rows = sorted(rows, key=lambda x: x[2], reverse=sort_descending)
        elif sort_column == "score":
            rows = sorted(rows, key=lambda x: x[3], reverse=sort_descending)

        # Display results in the table
        # Create table rows
        results_table.rows = [
            row for result_rows in rows
            for row in create_antenna_row(result_rows, page)
            #if row.visible  # Only visible rows
        ]
        
        # Update the page only if at least one row is visible
        #if results_table.rows:
        page.update()








    def load_locations(sort_by="score"):
        location_query = "SELECT DISTINCT location FROM results"
        locations = [row[0] for row in database_manager(location_query, fetchall=True)]

        rows = []
        for location in locations:
            avg_snr = calculate_avg_snr(location=location)
            score = calculate_snr_score(location=location)
            rows.append((location, avg_snr, score))

        # Sorting based on the selected column
        if sort_by == "location_name":
            rows = sorted(rows, key=lambda x: x[0], reverse=sort_descending)
        elif sort_by == "snr":
            rows = sorted(rows, key=lambda x: x[1], reverse=sort_descending)
        elif sort_by == "score":
            rows = sorted(rows, key=lambda x: x[2], reverse=sort_descending)

        locations_table.rows = [row for result_rows in rows for row in create_location_row(result_rows, page)]
        page.update()


    def open_url(url):
        if platform.system() == "Windows":
            webbrowser.open(url)
        elif platform.system() == "Linux" and "ANDROID_STORAGE" in os.environ:
            # Use an Android-specific call
            page.launch_url(url)
        else:
            # Fallback for other platforms
            webbrowser.open(url)




    def create_antenna_row(row, page):
        antenna_name = row[1]
        location = location_filter_dropdown.value  # Location from the dropdown filter
        #print(f"Row data: {row}")

        # Calculation of avg_rssi and score using the designated functions
        avg_rssi = calculate_avg_rssi(antenna_name=antenna_name, location=location)
        score = calculate_rssi_score(antenna_name=antenna_name, location=location)

        avg_rssi_text = "N/A" if avg_rssi is None else str(round(avg_rssi, 2))
        score_text = "N/A" if score is None else str(round(score, 2))
        
        url = row[4] if row[4] is not None else ""  # Ensure URL is present
        notes = row[5] if row[5] not in [None, ""] else "No Notes"
       
        
        # Text elements for the main row
        text_elements = [
            ft.Text(antenna_name, size=12),
            ft.Text(avg_rssi_text, size=12),
            ft.Text(score_text, size=12)
        ]
        
        # Additional detail row (visible on click)
        additional_info_row = ft.DataRow(
            cells=[
                ft.DataCell(
                    ft.TextButton(
                        text="Shop Link",
                        on_click=lambda e: open_url(url)
                    ) if url else ft.Text("No Link")
                ),
                ft.DataCell(ft.Text("Notes:", weight="bold", size=12)),
                ft.DataCell(ft.Text(notes))
            ],
            visible=False  # Temporarily set the row to 'visible'
        )


        # Main antenna row
        expandable_row = ft.DataRow(
            cells=[
                ft.DataCell(ft.Container(content=text_elements[0], alignment=ft.alignment.center)),
                ft.DataCell(ft.Container(content=text_elements[1], alignment=ft.alignment.center)),
                ft.DataCell(ft.Container(content=text_elements[2], alignment=ft.alignment.center))
            ],
            on_select_changed=lambda _: toggle_row(additional_info_row, text_elements, page)
        )

        return [expandable_row, additional_info_row]
    





    def create_location_row(row, page):
        location_name = row[0]
        avg_snr = round(row[1], 2)  # The average SNR for the location
        score = round(row[2], 2)  # The calculated score based on avg_snr
        score_text = "N/A" if score is None else str(score)

        text_elements = [
            ft.Text(location_name, size=12),
            ft.Text(str(avg_snr), size=12),
            ft.Text(score_text, size=12)
        ]

        # SQL query to determine the antenna with the best RSSI value for this location
        best_antenna = database_manager('''SELECT antenna_name, rssi FROM results WHERE location=? ORDER BY rssi DESC LIMIT 1''', (location_name,), fetchone=True)
        best_antenna_text = best_antenna[0] if best_antenna else "No Antenna Found"

        additional_info_row = ft.DataRow(
            cells=[
                ft.DataCell(ft.Text("Best antenna for this location:", weight="bold", size=12)),
                ft.DataCell(ft.Text(best_antenna_text, weight="bold", size=12)),
                ft.DataCell(ft.Text(""))
            ],
            visible=False
        )

        expandable_row = ft.DataRow(
            cells=[
                ft.DataCell(ft.Container(content=text_elements[0], alignment=ft.alignment.center)),  # Centered
                ft.DataCell(ft.Container(content=text_elements[1], alignment=ft.alignment.center)),  # Centered
                ft.DataCell(ft.Container(content=text_elements[2], alignment=ft.alignment.center))   # Centered
            ],
            on_select_changed=lambda _: toggle_row(additional_info_row, text_elements, page)
        )

        return [expandable_row, additional_info_row]
    












    
    def start_timer():
        global test_start_time
        test_start_time = datetime.now()

    def update_elapsed_time():
        if test_start_time is not None and not stop_sending:
            elapsed_time = datetime.now() - test_start_time
            hours, remainder = divmod(elapsed_time.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            elapsed_time_label.value = f"Elapsed Time: {hours:02}:{minutes:02}:{seconds:02}"
            page.update()



    def send_message(destination_node_id):
        global sent_message_id, messages_sent
        try:
            if visible_message_checkbox.value:
                sent_message = interface.sendText(
                    text=message_text_input.value,
                    destinationId=destination_node_id,
                    wantAck=True
                )
            else:
                sent_message = interface.sendData(
                    data=b'',
                    destinationId=destination_node_id,
                    wantAck=True
                )

            # Direct assignment of the ID
            sent_message_id = sent_message.id
            messages_sent += 1  # Increment message counter
            update_message_ack_display()  # Update GUI for sent messages
            #print(f"Sent message ID: {sent_message_id}")
        except Exception as ex:
            connection_status_text.value = f"Error: {str(ex)}"
            connection_status_icon.color = "red"
            page.update()





    

    def save_settings(e):
        global settings_saved

        validate_interval(interval_input)

        tcp_ip = tcp_ip_input.value if connection_type_dropdown.value == "TCP" else ""
        ble_device_name = ble_device_input.value if connection_type_dropdown.value == "BLE" else ""
        
        # Validation of the Destination Node ID
        destination_node_id = destination_node_input.value.strip()

        # Remove all exclamation marks and then add only one
        destination_node_id = destination_node_id.lstrip("!")  # Removes all leading exclamation marks
        destination_node_id = "!" + destination_node_id  # Adds a single exclamation mark

        # Update the input field with the correct Destination Node ID
        destination_node_input.value = destination_node_id
       


        visible_message = message_text_input.value if visible_message_checkbox.value else ""

        page.client_storage.set("antenna_name", antenna_name_input.value)
        page.client_storage.set("url", url_input.value or "")
        page.client_storage.set("notes", notes_input.value or "")
        page.client_storage.set("location", location_input_dropdown.value if location_input_dropdown.value != "New Location" else new_location_input.value)
        page.client_storage.set("connection_type", connection_type_dropdown.value)
        page.client_storage.set("tcp_ip", tcp_ip)
        page.client_storage.set("ble_device_name", ble_device_name)
        page.client_storage.set("destination_node_id", destination_node_id)
        page.client_storage.set("visible_message", message_text_input.value or "")
        page.client_storage.set("send_visible_message", visible_message_checkbox.value)
        settings_saved = True
        page.overlay.append(ft.SnackBar(ft.Text("Settings saved! Make sure the BLE/TCP node is not connected to any other device before you start the test! "), open=True))
        page.update()



    def load_settings():
        try:
            # Load all locations from the database
            locations = ["New Location"] + [row[0] for row in database_manager("SELECT DISTINCT location FROM results", fetchall=True)]

            # Update the location dropdown with the new values
            location_input_dropdown.options = [ft.dropdown.Option(loc) for loc in locations]

            # Set the saved location value
            location_value = page.client_storage.get("location") or ""
            if location_value in locations:
                location_input_dropdown.value = location_value
                new_location_input.visible = False
                location_input_dropdown.visible = True
                cancel_location_button.visible = False
                save_button.disabled = False  # Enable the Save button when a valid location is loaded
            else:
                location_input_dropdown.value = "New Location"
                new_location_input.value = location_value
                new_location_input.visible = True
                location_input_dropdown.visible = False
                cancel_location_button.visible = True
                save_button.disabled = False  # Enable the Save button when a new location is entered

        except Exception as e:
            print(f"Error loading settings: {e}")

        # Load the remaining saved settings
        antenna_name_value = page.client_storage.get("antenna_name") or ""
        url_value = page.client_storage.get("url") or ""
        notes_value = page.client_storage.get("notes") or ""
        connection_type_value = page.client_storage.get("connection_type") or "TCP"
        tcp_ip_value = page.client_storage.get("tcp_ip") or ""
        ble_device_name_value = page.client_storage.get("ble_device_name") or ""
        destination_node_id_value = page.client_storage.get("destination_node_id") or ""
        visible_message_value = page.client_storage.get("visible_message") or ""
        send_visible_message_value = page.client_storage.get("send_visible_message") or False

        # Set the loaded values in the corresponding fields
        antenna_name_input.value = antenna_name_value
        url_input.value = url_value
        notes_input.value = notes_value
        connection_type_dropdown.value = connection_type_value
        tcp_ip_input.value = tcp_ip_value
        ble_device_input.value = ble_device_name_value
        destination_node_input.value = destination_node_id_value
        message_text_input.value = visible_message_value
        visible_message_checkbox.value = send_visible_message_value

        # Visibility based on the Connection Type
        tcp_ip_input.visible = connection_type_value == "TCP"
        ble_device_input.visible = connection_type_value == "BLE"
        message_text_input.visible = send_visible_message_value

        # Enable Save button when all required fields are filled
        save_button.disabled = not (
            antenna_name_input.value.strip() and
            location_input_dropdown.value and
            connection_type_dropdown.value and
            destination_node_input.value.strip()
        )

        # Update the page to display the changes
        page.update()



    def connect_to_device():
        global interface
        try:
            connection_status_icon.color = "yellow"
            connection_status_text.value = "Setting up connection..."
            page.update()

            connection_type = connection_type_dropdown.value
            tcp_ip = tcp_ip_input.value
            ble_device_name = ble_device_input.value

            if connection_type == "TCP":
                interface = meshtastic.tcp_interface.TCPInterface(hostname=tcp_ip)
            elif connection_type == "BLE":
                interface = meshtastic.ble_interface.BLEInterface(ble_device_name)

            pub.subscribe(on_receive, "meshtastic.receive")
            #print(f"Connected via {connection_type}")
            return True
        except Exception as ex:
            connection_status_icon.color = "red"
            connection_status_text.value = f"Connection error: {str(ex)}"
            page.update()
            return False


    # Queue for ACK processing directly within the existing flow
    def process_ack_queue():
        while not ack_queue.empty():
            ack_data = ack_queue.get()

            # Insert into the database
            try:
                query = '''
                    INSERT INTO results (antenna_name, url, notes, location, node_name, node_id, connection_type, address, timestamp, rssi, snr)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                '''
                params = (
                    ack_data['antenna_name'],
                    ack_data['url'],
                    ack_data['notes'],
                    ack_data['location'],
                    "Unknown Node",
                    ack_data['from_id'],
                    connection_type_dropdown.value,
                    tcp_ip_input.value if connection_type_dropdown.value == "TCP" else ble_device_input.value,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    ack_data['rssi'],
                    ack_data['snr']
                )
                database_manager(query, params, commit=True)
                #print("Data inserted successfully:", ack_data)
                page.overlay.append(ft.SnackBar(ft.Text(f"ACK received and logged"), open=True))
            except Exception as e:
                print(f"Error while inserting into database: {e}")
                page.overlay.append(ft.SnackBar(ft.Text(f"Error while inserting data: {e}"), open=True))

        # Update the UI after processing
        page.update()

    # on_receive remains unchanged, puts the data into the queue
    def on_receive(packet, interface):
        global acks_received
        from_id = packet.get("fromId", "")
        request_id = packet.get("decoded", {}).get("requestId", None)

        rssi = packet.get("rxRssi", None)
        snr = packet.get("rxSnr", None)

        # Check if the ACK was received for the correct message
        if from_id == destination_node_input.value and request_id == sent_message_id:
            if request_id is not None:
                acks_received += 1  # Increment ACK counter
                ack_data = {
                    'antenna_name': antenna_name_input.value,
                    'url': url_input.value,
                    'notes': notes_input.value,
                    'location': location_input_dropdown.value if location_input_dropdown.value != "New Location" else new_location_input.value,
                    'from_id': from_id,
                    'rssi': rssi,
                    'snr': snr
                }
                ack_queue.put(ack_data)  # Put ACK data into the queue
                update_message_ack_display()  # Update GUI for received ACKs

                # Process the ACK data immediately upon reception
                process_ack_queue()



    def disable_data_buttons():
        delete_antenna_button.disabled = True
        delete_location_button.disabled = True
        delete_database_button.disabled = True
        export_csv_button.disabled = True
        import_db_button.disabled = True  # Import DB button disabled
        export_db_button.disabled = True  # Export DB button disabled
        page.update()
      



    def enable_data_buttons():
        delete_antenna_button.disabled = False
        delete_location_button.disabled = False
        delete_database_button.disabled = False
        export_csv_button.disabled = False
        import_db_button.disabled = False  # Import DB button enabled
        export_db_button.disabled = False  # Export DB button enabled
        page.update()
      








    def start_sending(e):
        global stop_sending, messages_sent, acks_received, test_running
        test_running = True
        stop_sending = False
        messages_sent = 0  # Reset message counter
        acks_received = 0  # Reset ACK counter
        update_message_ack_display()  # Set GUI counters to 0

        # Reset the display
        messages_sent_value.value = "0"
        acks_received_value.value = "0"
        page.update()

        # Disable data buttons when the test starts
        disable_data_buttons()
        global settings_saved

        if not settings_saved:
            page.overlay.append(ft.SnackBar(ft.Text("Please complete all fields and save settings before starting the test."), open=True))
            page.update()
            return

        # Check if "New Location" is selected and not saved
        if location_input_dropdown.value == "New Location" and not new_location_input.value.strip():
            page.overlay.append(ft.SnackBar(ft.Text("Please complete all fields and save settings before starting the test."), open=True))
            page.update()
            return

        # Check if all required fields are filled
        if not (
            antenna_name_input.value.strip() and
            location_input_dropdown.value and
            connection_type_dropdown.value and
            destination_node_input.value.strip()
        ):
            page.overlay.append(ft.SnackBar(ft.Text("Please complete all fields and save settings before starting the test."), open=True))
            page.update()
            return

        destination_node_id = destination_node_input.value
        countdown_label.value = ""

        if interface is None:
            if not connect_to_device():
                return

        # Get the interval from the input field
        interval = int(interval_input.value) if interval_input.value.isdigit() else 30

        progress_bar.visible = True
        simulate_connection_setup(destination_node_id)

        start_timer()

        # Main test loop
        while not stop_sending:
            # Countdown before sending the next message
            countdown(interval)
            if stop_sending:
                break
            
            # Send message
            send_message(destination_node_id)
            
            # Process the ACK queue after each message
            process_ack_queue()
            
            # Update the elapsed time
            update_elapsed_time()
            page.update()

        # Ensure all ACKs are processed
        stop_sending_messages(None)






    def stop_sending_messages(e):
        global stop_sending, interface, test_running
        test_running = False
        stop_sending = True
        progress_bar.visible = False
        countdown_label.value = ""
        test_start_time = None
        elapsed_time_label.value = "Elapsed Time: 00:00:00"

        if interface is not None:
            try:
                interface.close()
                interface = None
                connection_status_icon.color = "red"
                connection_status_text.value = "No connection"
            except Exception as ex:
                page.overlay.append(ft.SnackBar(ft.Text(f"Error: {str(ex)}"), open=True))

        page.overlay.append(ft.SnackBar(ft.Text("Test stopped by user."), open=True))
        enable_data_buttons()
        page.update()





    def simulate_connection_setup(destination_node_id):
        global messages_sent
        progress_bar.value = 0
        for i in range(1, 31):
            if stop_sending:
                stop_sending_messages(None)
                return
            progress_bar.value = i / 30
            connection_status_text.value = f"Setting up connection... {i * 100 // 30}%"
            page.update()
            time.sleep(1)

        if not stop_sending:
            connection_status_icon.color = "green"
            connection_status_text.value = "Connected"
            page.update()

            send_message(destination_node_id)


        progress_bar.visible = False
        page.update()



    def countdown(seconds):
        for i in range(seconds, 0, -1):
            if stop_sending:
                break
            countdown_text = f"Next message in {i} seconds..."
            countdown_label.value = countdown_text
            update_elapsed_time()
            page.update()
            time.sleep(1)  # Simulates the countdown wait time
        if not stop_sending:
            countdown_label.value = "Sending message..."
            page.update()



    def on_column_click(column_name, tab_index):
        global sort_column, sort_descending

        # If the same column is clicked, toggle the sort order
        if sort_column == column_name:
            sort_descending = not sort_descending
        else:
            sort_column = column_name
            sort_descending = True  # Default to descending order on first click of a new column

        #print(f"Clicked on column: {column_name}, sort_column: {sort_column}, sort_descending: {sort_descending}")

        # Reload the appropriate table based on the tab index
        if tab_index == 2:  # Antennas table
            load_results(location_filter_dropdown.value)
        elif tab_index == 3:  # Locations table
            load_locations(sort_by=sort_column)

        # Update the page to display the sorting
        page.update()








    def on_location_filter_change(e):
        selected_location = location_filter_dropdown.value
        load_results(selected_location)
        page.update()

    def on_location_dropdown_change(e):
        selected_location = e.control.value

        if selected_location == "All Locations":
            load_locations()
        else:
            load_locations(selected_location)



    def load_data_tab():
        if not os.path.exists(DATABASE_FILEPATH):
            disable_data_buttons()
            return

        # Fetch the distinct entries of antennas and locations
        antennas = [row[0] for row in database_manager("SELECT DISTINCT antenna_name FROM results", fetchall=True)]
        locations = [row[0] for row in database_manager("SELECT DISTINCT location FROM results", fetchall=True)]

        # Still fill the dropdown menus, even if the buttons remain disabled
        antenna_dropdown.options = [ft.dropdown.Option(ant) for ant in antennas]
        location_dropdown.options = [ft.dropdown.Option(loc) for loc in locations]

        # Only activate buttons when no test is running
        if not test_running:
            delete_antenna_button.disabled = len(antennas) == 0
            delete_location_button.disabled = len(locations) == 0

        page.update()






    def confirm_delete(action):
        def perform_action(e):
            page.overlay.pop()  # Close the dialog after confirmation
            action()  # Execute the passed action

        page.overlay.append(
            ft.SnackBar(
                content=ft.Text("Are you sure you want to delete?"),
                action="Confirm",
                on_action=perform_action,
                open=True,
                action_color="green",
                show_close_icon=True
            )
        )
        page.update()

    


    def delete_antenna(e):
        if test_running:
            page.overlay.append(ft.SnackBar(ft.Text("Cannot delete antenna while test is running."), open=True))
            return

        if not os.path.exists(DATABASE_FILEPATH):
            page.overlay.append(ft.SnackBar(ft.Text("No database available."), open=True))
            return

        def perform_deletion():
            antenna_to_delete = antenna_dropdown.value
            if antenna_to_delete:
                query = "DELETE FROM results WHERE antenna_name = ?"
                database_manager(query, (antenna_to_delete,), commit=True)
                load_data_tab()
                load_settings()
                page.overlay.append(ft.SnackBar(ft.Text("Antenna deleted."), open=True))
                page.update()

        # Show confirmation dialog
        confirm_delete(perform_deletion)



        

    def delete_location(e):
        if test_running:
            page.overlay.append(ft.SnackBar(ft.Text("Cannot delete location while test is running."), open=True))
            return

        if not os.path.exists(DATABASE_FILEPATH):
            page.overlay.append(ft.SnackBar(ft.Text("No database available."), open=True))
            return

        def perform_deletion():
            location_to_delete = location_dropdown.value
            if location_to_delete:
                query = "DELETE FROM results WHERE location = ?"
                database_manager(query, (location_to_delete,), commit=True)
                load_data_tab()
                load_settings()
                page.overlay.append(ft.SnackBar(ft.Text("Location deleted."), open=True))
                page.update()

        # Show confirmation dialog
        confirm_delete(perform_deletion)




    def delete_database(e):
        if test_running:
            page.overlay.append(ft.SnackBar(ft.Text("Cannot delete database while test is running."), open=True))
            return

        if not os.path.exists(DATABASE_FILEPATH):
            page.overlay.append(ft.SnackBar(ft.Text("No database available."), open=True))
            return

        def perform_deletion():
            try:
                # Safely close all open connections
                database_manager("VACUUM")  # SQLite specific: Empties the DB, closes, and cleans up

                # Now delete
                if os.path.exists(DATABASE_FILEPATH):
                    os.remove(DATABASE_FILEPATH)
                    page.overlay.append(ft.SnackBar(ft.Text("Database deleted successfully."), open=True))
                    update_ui_after_db_change()
                    show_restart_popup(page)

            except PermissionError as ex:
                page.overlay.append(ft.SnackBar(ft.Text(f"Error: {str(ex)}"), open=True))
                page.update()

        # Show confirmation dialog
        confirm_delete(perform_deletion)

        




    def show_restart_popup(page):
        popup = ft.AlertDialog(
            modal=True,
            title=ft.Text("App Restart Required"),
            content=ft.Text("The database has been deleted. Please restart the app manually."),
            actions=[],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        # Instead of page.dialog = popup:
        page.overlay.append(popup)  # Add the dialog to the overlay list
        popup.open = True
        page.update()




    def export_db(e):
        if not os.path.exists(DATABASE_FILEPATH):
            page.overlay.append(ft.SnackBar(ft.Text("No database available."), open=True))
            return

        try:
            # Export the database to the specified path
            exported_db_file = os.path.join(CSV_EXPORT_PATH, f"{os.path.splitext(DATABASE_FILENAME)[0]}_{timestamp}.db")
            with open(DATABASE_FILEPATH, "rb") as db_source:
                with open(exported_db_file, "wb") as db_dest:
                    db_dest.write(db_source.read())

            # Show success message
            if platform.system() == "Linux" and "ANDROID_STORAGE" in os.environ:
                page.overlay.append(
                    ft.SnackBar(
                        content=ft.Text(f"Database exported to {exported_db_file}"),
                        action="OK",
                        on_action=lambda e: page.overlay.clear(),
                        action_color="green",
                        open=True,
                    )
                )
            else:
                page.overlay.append(
                    ft.SnackBar(
                        content=ft.Text(f"Database exported to {exported_db_file}"),
                        action="Open",
                        on_action=lambda e: open_exported_file(page, exported_db_file),
                        action_color="green",
                        open=True,
                    )
                )

        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f"Error during DB export: {str(ex)}"), open=True))

        page.update()


    def import_database(filepath):
        try:
            database_manager("DELETE FROM results", commit=True)

            import_conn = sqlite3.connect(filepath)
            import_cursor = import_conn.cursor()

            import_cursor.execute("SELECT * FROM results")
            rows = import_cursor.fetchall()
            for row in rows:
                query = '''INSERT INTO results (id, antenna_name, url, notes, location, node_name, node_id, connection_type, address, timestamp, rssi, snr)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''
                database_manager(query, row, commit=True)

            import_conn.close()

            # Show success message
            page.overlay.append(ft.SnackBar(ft.Text("Database imported successfully!"), open=True))
            page.update()

        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f"Error during DB import: {str(ex)}"), open=True))
            page.update()


    def import_db(e):
        if platform.system() == "Windows":
            # Windows: Use FilePicker as before
            def on_file_picked(result: ft.FilePickerResultEvent):
                if result.files is not None and len(result.files) > 0:
                    selected_file = result.files[0].path
                    try:
                        import_database(selected_file)
                    except Exception as ex:
                        page.overlay.append(ft.SnackBar(ft.Text(f"Error during DB import: {str(ex)}"), open=True))
                        page.update()

            if not hasattr(page, "file_picker"):
                page.file_picker = ft.FilePicker(on_result=on_file_picked)
                page.overlay.append(page.file_picker)
                page.update()

            page.file_picker.pick_files(
                allowed_extensions=["db"],
                dialog_title="Select Database to Import",
                initial_directory=CSV_EXPORT_PATH
            )
        else:
            # Android: Scan known directory for .db files
            CSV_IMPORT_PATH = "/storage/emulated/0/Download"
            if not os.access(CSV_IMPORT_PATH, os.R_OK):
                show_permission_dialog()
                return
        
            db_files = [f for f in os.listdir(CSV_IMPORT_PATH) if f.endswith('.db')]
            if not db_files:
                page.overlay.append(ft.SnackBar(ft.Text("No database files found in the Download folder."), open=True))
                page.update()
                return

            db_dropdown = ft.Dropdown(
                label="Select Database File",
                options=[ft.dropdown.Option(f) for f in db_files],
                width=300
            )

            def on_db_selected(ev):
                selected_file = db_dropdown.value
                if selected_file:
                    try:
                        import_database(os.path.join(CSV_IMPORT_PATH, selected_file))
                        popup.open = False  # Close the dialog after selection
                        page.update()
                    except Exception as ex:
                        page.overlay.append(ft.SnackBar(ft.Text(f"Error during DB import: {str(ex)}"), open=True))
                        page.update()
                else:
                    page.overlay.append(ft.SnackBar(ft.Text("Please select a database file to import."), open=True))
                    page.update()

            def on_cancel(ev):
                popup.open = False  # Close the dialog without importing
                page.update()

            import_button = ft.ElevatedButton(text="Import", on_click=on_db_selected)
            cancel_button = ft.ElevatedButton(text="Cancel", on_click=on_cancel)

            popup = ft.AlertDialog(
                modal=True,
                title=ft.Text("Import Database"),
                content=ft.Column(
                    controls=[
                        db_dropdown,
                        ft.Row([import_button, cancel_button], alignment="center")
                    ]
                ),
                actions=[],
                actions_alignment=ft.MainAxisAlignment.END,
            )

            page.overlay.append(popup)
            popup.open = True
            page.update()






    def export_csv(e):
        if not os.path.exists(DATABASE_FILEPATH):
            page.overlay.append(ft.SnackBar(ft.Text("No database available."), open=True))
            return

        try:
            # Query all results
            rows = database_manager("SELECT * FROM results", fetchall=True)
            headers = ["id", "antenna_name", "url", "notes", "location", "node_name", "node_id", "connection_type", "address", "timestamp", "rssi", "snr"]

            # Write CSV file
            with open(EXPORT_CSV_FILE, "w") as f:
                f.write(",".join(headers) + "\n")
                for row in rows:
                    f.write(",".join(map(str, row)) + "\n")

            # Show success message
            if platform.system() == "Linux" and "ANDROID_STORAGE" in os.environ:
                page.overlay.append(
                    ft.SnackBar(
                        content=ft.Text(f"CSV exported to {EXPORT_CSV_FILE}"),
                        action="OK",
                        on_action=lambda e: page.overlay.clear(),
                        action_color="green",
                        open=True,
                    )
                )
            else:
                page.overlay.append(
                    ft.SnackBar(
                        content=ft.Text(f"CSV exported to {EXPORT_CSV_FILE}"),
                        action="Open",
                        on_action=lambda e: open_exported_file(page, EXPORT_CSV_FILE),
                        action_color="green",
                        open=True,
                    )
                )

        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f"Error during CSV export: {str(ex)}"), open=True))

        page.update()



    def open_exported_file(page, filepath):
        if platform.system() == "Linux" and "ANDROID_STORAGE" in os.environ:
            # Use the Android-compatible way to open the file
            page.launch_url(f"file://{filepath}")
        else:
            # Fallback for other platforms (Windows, Linux desktop)
            os.startfile(os.path.dirname(filepath))




    def update_ui_after_db_change():
        """Updates the UI elements depending on whether the database exists."""
        if os.path.exists(DATABASE_FILEPATH):
            enable_data_buttons()
            db_path_label.value = f"Database Path: {DATABASE_FILEPATH}"
            db_path_label.visible = True
        else:
            disable_data_buttons()
            db_path_label.visible = False
        page.update()

    interval_input = ft.TextField(
        label="Interval (seconds)",
        width=300,
        value="30",
        on_blur=lambda e: validate_interval(e.control),
    )

    def validate_interval(field):
        try:
            interval = int(field.value)
            if interval < 30:
                field.value = "30"
            page.update()
        except ValueError:
            field.value = "30"
            page.update()



    start_button = ft.ElevatedButton(text="Start", on_click=start_sending, width=140)
    stop_button = ft.ElevatedButton(text="Stop", on_click=stop_sending_messages, width=140)
    connection_status_icon = ft.Icon(name="lens", color="red", size=20)
    connection_status_text = ft.Text(value="No connection", text_align="center")
    countdown_label = ft.Text(value="", size=16, text_align="center")
    elapsed_time_label = ft.Text(value="Elapsed Time: 00:00:00", size=16, text_align="center")
    progress_bar = ft.ProgressBar(width=200, height=10, visible=False)

    messages_sent_label = ft.Text(value="Messages sent: ", text_align="center", size=16, weight="bold")
    messages_sent_value = ft.Text(value="0", text_align="center", size=16, weight="bold")
    acks_received_label = ft.Text(value="ACKs received: ", text_align="center", size=16, weight="bold")
    acks_received_value = ft.Text(value="0", text_align="center", size=16, weight="bold")

    watermark_image = ft.Image(src="assets/icon.png", opacity=0.1, width=200, height=200)

    test_tab = ft.Stack(
        controls=[
            ft.Container(content=watermark_image, alignment=ft.alignment.center),
            ft.Column(
                controls=[
                    ft.Container(height=25),
                    ft.Row(controls=[messages_sent_label, messages_sent_value], alignment="center"),
                    ft.Row(controls=[acks_received_label, acks_received_value], alignment="center"),
                    ft.Row(controls=[countdown_label], alignment="center"),
                    ft.Row(controls=[elapsed_time_label], alignment="center"),
                    ft.Container(expand=True),  # Flexible Container to push the lower elements down
                    ft.Row(controls=[connection_status_icon, connection_status_text], alignment="center", spacing=10),
                    ft.Row(controls=[progress_bar], alignment="center"),
                    ft.Container(height=10),
                    ft.Row(controls=[start_button, stop_button], alignment="center", spacing=10),
                    ft.Container(height=20),
                ],
                alignment="start",
                expand=True
            ),
        ],
        expand=True
    )

    antenna_name_input = ft.TextField(label="Antenna Name", width=300, max_length=15, on_change=on_setting_change)
    url_input = ft.TextField(label="Buy URL", width=300, on_change=on_setting_change)
    notes_input = ft.TextField(label="Notes", width=300, max_length=15, on_change=on_setting_change)

    # Use the database_manager instead of sqlite3 to load the locations
    locations = ["New Location"] + [row[0] for row in database_manager("SELECT DISTINCT location FROM results", fetchall=True)]

    location_input_dropdown = ft.Dropdown(
        label="Location",
        options=[ft.dropdown.Option("Choose Location", disabled=True)] + [ft.dropdown.Option(loc) for loc in locations if loc != "New Location"] + [ft.dropdown.Option("New Location")],
        value="Choose Location",
        on_change=lambda e: [on_setting_change(e), on_location_select_change(e.control)],
        width=300,
    )






    new_location_input = ft.TextField(label="New Location", visible=False, width=300, max_length=36)
    cancel_location_button = ft.TextButton(text="Cancel", visible=False, on_click=lambda e: cancel_new_location_input(), width=100)

    def on_location_select_change(dropdown):
        if dropdown.value == "New Location":
            new_location_input.value = ""  # Clear input field
            location_input_dropdown.visible = False
            new_location_input.visible = True
            cancel_location_button.visible = True
            save_button.disabled = True  # Disable save button until input is provided
        elif dropdown.value == "Choose Location":
            save_button.disabled = True  # Disable save button if "Choose Location" is selected
        else:
            save_button.disabled = False  # Enable save button for valid location
        page.update()




    def on_new_location_input_change(e):
        if new_location_input.value.strip():  # Enable save button if input is not empty
            save_button.disabled = False
        else:
            save_button.disabled = True
        page.update()

    new_location_input = ft.TextField(
        label="New Location", 
        visible=False, 
        width=300, 
        max_length=36,
        on_change=on_new_location_input_change
    )

    def cancel_new_location_input():
        location_input_dropdown.visible = True
        location_input_dropdown.value = "Choose Location"  # Reset to "Choose Location"
        new_location_input.visible = False
        cancel_location_button.visible = False
        save_button.disabled = True  # Disable save button since "Choose Location" is selected
        page.update()

    connection_type_options = [ft.dropdown.Option("TCP")]
    if platform.system() == "Windows":
        connection_type_options.append(ft.dropdown.Option("BLE"))

    connection_type_dropdown = ft.Dropdown(
        label="Connection Type",
        options=connection_type_options,
        value="TCP",
        on_change=lambda e: [on_setting_change(e), on_connection_type_change(e)],
        width=300,
    )

    tcp_ip_input = ft.TextField(label="TCP/IP Address", width=300, visible=True, on_change=on_setting_change)
    ble_device_input = ft.TextField(label="BLE Device Name/Address", width=300, visible=False, on_change=on_setting_change)
    destination_node_input = ft.TextField(label="Destination Node ID", width=300, on_change=on_setting_change)

    visible_message_checkbox = ft.Checkbox(label="Send Visible Message", on_change=lambda e: [on_visible_message_change(e), on_setting_change(e)])
    message_text_input = ft.TextField(label="Message Text", width=300, visible=False, on_change=on_setting_change)

    save_button = ft.ElevatedButton(text="Save", on_click=save_settings, width=140, disabled=True)  # Button disabled by default
    setup_status_label = ft.Text(value="", size=16)

    setup_tab = ft.Container(
        content=ft.Column(
            controls=[
                ft.Container(height=5),
                antenna_name_input,
                url_input,
                notes_input,
                location_input_dropdown,
                new_location_input,
                ft.Container(content=cancel_location_button, alignment=ft.alignment.center),  # Move the Cancel button under the dropdown
                connection_type_dropdown,
                tcp_ip_input,
                ble_device_input,
                destination_node_input,
                interval_input,  # The interval field
                visible_message_checkbox,
                message_text_input,
                save_button,
                setup_status_label
            ],
            alignment="center",
            spacing=10,
            scroll=ft.ScrollMode.AUTO
        ),
        padding=ft.Padding(20, 20, 20, 20)
    )


    # Use the database_manager to query the database
    locations = ["All Locations"] + [row[0] for row in database_manager("SELECT DISTINCT location FROM results", fetchall=True)]

    location_filter_dropdown = ft.Dropdown(
        label="Filter by Location",
        options=[ft.dropdown.Option("All Locations")] + [ft.dropdown.Option(loc) for loc in locations],
        value="All Locations",
        on_change=on_location_filter_change,
        width=300,
    )



    score_column = ft.DataColumn(
        label=ft.Text("Score", weight="bold", size=12),
        on_sort=lambda _: on_column_click("score")
    )

    results_table = ft.DataTable(
        columns=[
            ft.DataColumn(
                label=ft.Container(
                    content=ft.Text("Antenna", weight="bold", size=13),
                    width=100,
                    alignment=ft.alignment.center  # Center the title
                ),
                on_sort=lambda _: on_column_click("antenna_name", 2)  # Adjust tab index
            ),
            ft.DataColumn(
                label=ft.Container(
                    content=ft.Text("RSSI", weight="bold", size=13),
                    width=50,
                    alignment=ft.alignment.center  # Center the title
                ),
                on_sort=lambda _: on_column_click("rssi", 2)  # Adjust tab index
            ),
            ft.DataColumn(
                label=ft.Container(
                    content=ft.Text("Score", weight="bold", size=13),
                    width=50,
                    alignment=ft.alignment.center  # Center the title
                ),
                on_sort=lambda _: on_column_click("score", 2)  # Adjust tab index
            )
        ],
        rows=[],
        column_spacing=1,
    )

    locations_table = ft.DataTable(
        columns=[
            ft.DataColumn(
                label=ft.Container(
                    content=ft.Text("Location", weight="bold", size=13),
                    width=100,
                    alignment=ft.alignment.center
                ),
                on_sort=lambda _: on_column_click("location_name", 3)  # Adjust tab index
            ),
            ft.DataColumn(
                label=ft.Container(
                    content=ft.Text("Avg SNR", weight="bold", size=13),
                    width=60,
                    alignment=ft.alignment.center
                ),
                on_sort=lambda _: on_column_click("snr", 3)  # Adjust tab index
            ),
            ft.DataColumn(
                label=ft.Container(
                    content=ft.Text("Score", weight="bold", size=13),
                    width=60,
                    alignment=ft.alignment.center
                ),
                on_sort=lambda _: on_column_click("score", 3)  # Adjust tab index
            )
        ],
        rows=[],
        column_spacing=1,
    )

    antennas_tab = ft.Container(
        content=ft.Column(
            controls=[
                ft.Container(height=20),
                ft.Row(
                    controls=[location_filter_dropdown],
                    alignment="center",
                    expand=False
                ),
                ft.Container(height=20),
                ft.Container(
                    content=ft.ListView(
                        controls=[results_table],
                        expand=True,
                        spacing=0,
                        padding=ft.Padding(0, 0, 0, 0)
                    ),
                    expand=True
                )
            ],
            alignment="center",
            spacing=0,
            expand=True
        ),
        padding=ft.Padding(0, 10, 0, 10),
        expand=True
    )

    locations_tab = ft.Container(
        content=ft.Column(
            controls=[
                ft.Container(height=20),
                #ft.Row(
                #    controls=[locations_dropdown],
                #    alignment="center",
                #    expand=False
                #),
                ft.Container(height=20),
                ft.Container(
                    content=ft.ListView(
                        controls=[locations_table],
                        expand=True,
                        spacing=0,
                        padding=ft.Padding(0, 0, 0, 0)
                    ),
                    expand=True
                )
            ],
            alignment="center",
            spacing=0,
            expand=True
        ),
        padding=ft.Padding(0, 10, 0, 10),
        expand=True
    )
            
    guide_tab = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text("Meshtastic Antenna Tester Guide", weight="bold", size=20),
                ft.Container(height=10),
                ft.Text("Overview:", weight="bold", size=16),
                ft.Text(
                    "The *Meshtenna* Meshtastic Antenna Tester is a tool designed to compare the performance of different antennas at various locations. "
                    "It measures and analyzes signal strength (RSSI) and signal-to-noise ratio (SNR) to help you identify the best antenna for specific conditions. "
                    "This tool uses a portable test node (TCP client, heltec v3 is recommended) to gather data at different locations and a fixed destination node for consistent measurements."
                ),
                ft.Container(height=5),
                ft.Text("Permissions on Android:", weight="bold", size=14),
                ft.Text(
                    "This app requires permission to access the Download folder to import and export database files. "
                    "When you first open the app, you may be prompted to grant this permission. "
                    "If you deny the permission, you can grant it later by going to your device's app settings. "
                    "When prompted, please grant the necessary permissions to ensure the app functions correctly."
                ),
                ft.Container(height=10),
                ft.Text("Important Notice TCP/BLE:", weight="bold", size=16),
                ft.Text(
                    "Please make sure that the node you are connecting to (BLE/TCP) is not already connected to any other device. "
                    "A Meshtastic node can only maintain one active connection at a time. If the node is already in use, the connection attempt will fail without proper error messages and error handling. In such a case, restart the app and reconnect."
                ),
                ft.Container(height=10),
                ft.Text("Tabs and Their Functions:", weight="bold", size=16),
                ft.Text("Test Tab:", weight="bold", size=14),
                ft.Text(
                    "This tab is the core of the application where tests are conducted. You connect to a Meshtastic device (the portable test node) using TCP. "
                    "Messages are sent to a fixed destination node, which should always remain in the same location with the same antenna setup to ensure consistent results. "
                    "The number of messages sent are displayed in real-time. A countdown timer shows when the next message will be sent. "
                    "Acknowledgments (ACKs) are not displayed in real-time but are checked periodically, similar to checking messages on a voicemail system. "
                    "The number of ACKs received is updated after each interval, and the connection status is visualized with an icon (green = connected, red = no connection)."
                ),
                ft.Container(height=5),
                ft.Text("Setup Tab:", weight="bold", size=14),
                ft.Text(
                    "In this tab, you configure the settings for your test. You need to input the 'Antenna Name', 'Buy URL', 'Notes', 'Location', and select the 'Connection Type'. "
                    "If you're using a TCP connection, provide the IP address of your portable test node. The 'Destination Node ID' is critical and should always refer to the fixed, "
                    "stationary node with a constant antenna setup. Changing the setup of this node requires deleting the database and starting fresh."
                ),
                ft.Container(height=5),
                ft.Text("Antennas Tab:", weight="bold", size=14),
                ft.Text(
                    "This tab displays and sorts the results of tested antennas. You can sort by antenna name, average RSSI, or calculated score. "
                    "Clicking on a row reveals additional information like shop links and notes. The score is based on RSSI values, allowing for easy comparison of antenna performance at specific locations."
                ),
                ft.Container(height=5),
                ft.Text("Locations Tab:", weight="bold", size=14),
                ft.Text(
                    "In this tab, you can view results for different locations. Similar to the Antennas tab, locations can be sorted by name, average SNR, or calculated score. "
                    "The best-performing antenna for each location is highlighted based on test results, making it easier to select the optimal setup for each environment."
                ),
                ft.Container(height=5),
                ft.Text("Data Tab:", weight="bold", size=14),
                ft.Text(
                    "This tab allows you to manage your data by deleting specific antennas or locations, or even the entire database. "
                    "You can also export test results as a CSV file or the entire database for further analysis in other programs."
                ),
                ft.Container(height=5),
                ft.Text("Importing a Database on Android:", weight="bold", size=14),
                ft.Text(
                    "On Android devices, the file picker is not available. To import a database, place the `.db` file in the `Download` folder of your device. "
                    "Then, go to the 'Data' tab in the app and tap 'Import DB'. You will see a list of available `.db` files to select from."
                ),
                ft.Container(height=5),
                ft.Text("Exporting Data:", weight="bold", size=14),
                ft.Text(
                    "When exporting data, the exported CSV or database file is saved to the `Documents` folder on Windows or the `Download` folder on Android. "
                    "On Windows, after exporting, you can open the file or folder directly by clicking 'Open' in the Snackbar. "
                    "On Android, you will receive a confirmation message, and you can access the exported files using a file manager app."
                ),
                ft.Container(height=5),
                ft.Text("Guide Tab:", weight="bold", size=14),
                ft.Text(
                    "This tab provides a detailed guide on how to use the app, including the purpose of each tab and instructions for setting up your tests."
                ),
                ft.Container(height=10),
                ft.Text("Technical Explanations:", weight="bold", size=16),
                ft.Text("RSSI (Received Signal Strength Indicator):", weight="bold", size=14),
                ft.Text(
                    "RSSI indicates the strength of the received signal in dBm. A higher value (closer to 0) means a stronger signal quality. "
                    "Typical values range from -120 dBm (very weak) to 0 dBm (very strong). RSSI is used to evaluate the quality of the connection between two Meshtastic devices."
                ),
                ft.Container(height=5),
                ft.Text("SNR (Signal-to-Noise Ratio):", weight="bold", size=14),
                ft.Text(
                    "SNR measures the ratio between the received signal and background noise, expressed in decibels (dB). "
                    "A higher value indicates better signal quality. Negative SNR values mean that the noise is stronger than the signal, indicating a poor connection. "
                    "SNR is particularly useful for evaluating environmental conditions at a location."
                ),
                ft.Container(height=5),
                ft.Text("Destination Node ID:", weight="bold", size=14),
                ft.Text(
                    "The Destination Node ID is the unique identifier of the fixed, stationary Meshtastic device to which all test messages are sent. "
                    "This node should remain in a consistent setup (same location, same antenna) to ensure reliable and comparable results. "
                    "If the setup of this node changes, you must delete the database and start fresh with new tests."
                ),
                ft.Container(height=10),
                ft.Text("Scores and Their Calculation:", weight="bold", size=16),
                ft.Text("Antenna Score:", weight="bold", size=14),
                ft.Text(
                    "The Antenna Score is calculated on a scale of 1 to 10 based on the average RSSI value for a specific antenna at a specific location. "
                    "The score allows for the comparison of antenna performance under identical conditions. "
                    "The score is determined by comparing the average RSSI of the antenna against the minimum and maximum RSSI values recorded for that location."
                ),
                ft.Container(height=5),
                ft.Text("Location Score:", weight="bold", size=14),
                ft.Text(
                    "The Location Score is also calculated on a scale of 1 to 10, but it is based on the average SNR value for a location. "
                    "This score helps evaluate the suitability of a location for communication, taking into account environmental factors like noise. "
                    "Scores are calculated by comparing the average SNR of the location with the minimum and maximum SNR values across all tested locations."
                ),
                ft.Container(height=10),
                ft.Text("*Note:*", weight="bold", size=14),
                ft.Text(
                    "This app was developed by OE3JGW / Jürgen Waissnix. If you want to support me, you can do so via PayPal at waissnix@gmail.com. You can also use this email address for support inquiries for this app."
                ),
            ],
            spacing=10,
            alignment="center",
            scroll=ft.ScrollMode.AUTO
        ),
        padding=ft.Padding(20, 20, 20, 20),
    )


    antenna_dropdown = ft.Dropdown(label="Select Antenna to Delete", options=[], width=300)
    location_dropdown = ft.Dropdown(label="Select Location to Delete", options=[], width=300)
    delete_antenna_button = ft.ElevatedButton(text="Delete Antenna", on_click=delete_antenna, width=300)
    delete_location_button = ft.ElevatedButton(text="Delete Location", on_click=delete_location, width=300)
    delete_database_button = ft.ElevatedButton(text="Delete Database", on_click=delete_database, width=300)
    export_csv_button = ft.ElevatedButton(text="Export to CSV", on_click=export_csv, width=300)
    db_path_label = ft.Text(value=f"Database Path: {DATABASE_FILEPATH}", size=12, visible=False)
    export_status_label = ft.Text(value="", size=12, visible=False)
    import_db_button = ft.ElevatedButton(text="Import DB", on_click=import_db, width=300)
    export_db_button = ft.ElevatedButton(text="Export DB", on_click=export_db, width=300)

    data_tab = ft.Container(
        content=ft.Column(
            controls=[
                db_path_label,
                ft.Column(controls=[antenna_dropdown, delete_antenna_button], alignment="center"),
                ft.Container(padding=ft.Padding(top=40, right=0, bottom=0, left=0)),
                ft.Column(controls=[location_dropdown, delete_location_button], alignment="center"),
                ft.Container(expand=True),  # Flexible container that pushes lower elements down
                delete_database_button,
                export_csv_button,
                export_status_label,
                export_db_button,  # New Export DB Button
                import_db_button,  # New Import DB Button
                ft.Container(padding=ft.Padding(top=20, right=0, bottom=0, left=0)),
            ],
            spacing=10,
            alignment="center",
            expand=True
        ),
        padding=ft.Padding(20, 20, 20, 20),
        expand=True
    )

    def on_tab_change(e):
        selected_index = e.control.selected_index

        if selected_index == 1:
            load_settings()
        if selected_index == 2:
            load_results()
        elif selected_index == 3:
            load_locations()
        elif selected_index == 4:
            #print("Test status: " + str(test_running))
            if test_running:
                disable_data_buttons()
            else:
                enable_data_buttons()
            load_data_tab()

    tabs = ft.Tabs(
        selected_index=0,
        on_change=on_tab_change,
        tabs=[
            ft.Tab(text="Test", content=test_tab),
            ft.Tab(text="Setup", content=setup_tab),
            ft.Tab(text="Antennas", content=antennas_tab),
            ft.Tab(text="Locations", content=locations_tab),
            ft.Tab(text="Data", content=data_tab),
            ft.Tab(text="Guide", content=guide_tab)
        ],
        expand=1
    )

    padding_container = ft.Container(height=30)

    page.add(padding_container, tabs)

    load_settings()

    page.window.width = 360
    page.window.height = 640
    page.window.resizable = True
    page.window.expand = True
    page.update()
ft.app(target=main)
