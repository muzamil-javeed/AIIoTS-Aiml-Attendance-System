import os
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from geopy.distance import geodesic
from streamlit_js_eval import get_geolocation
from PIL import Image
import io
import pymongo
from dotenv import load_dotenv
# Load environment variables from .env file
load_dotenv()

# Get the connection string from environment variables
connection_string = os.getenv("MONGODB_CONNECTION_STRING")

# Define the allowed location coordinates (latitude, longitude)
ALLOWED_LOCATION = (34.1011, 74.8090)  # Example coordinates
MAX_DISTANCE_KM = 10.0  # Maximum allowed distance in kilometers

# Connect to MongoDB
client = pymongo.MongoClient(connection_string)
db = client["attendance_db"]
attendance_collection = db["attendance"]

def save_image(img):
    image = Image.open(img)
    image = image.resize((150, 150))  # Resize to 150x150 pixels
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    return img_byte_arr.getvalue()

def log_arrival(name, date, photo):
    # Convert date to datetime for MongoDB query
    query_date = datetime.combine(date, datetime.min.time())
    
    if attendance_collection.find_one({"Name": name, "Date": query_date}):
        return False, "Arrival already logged for today."

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    photo_data = save_image(photo)

    new_entry = {
        'Name': name,
        'Date': query_date,
        'Arrival Time': datetime.now().strftime('%I:%M %p'),
        'Leaving Time': None,
        'Hours Present': None,
        'Arrival Photo': photo_data,
        'Leaving Photo': None
    }

    attendance_collection.insert_one(new_entry)
    return True, "Arrival logged successfully."

def log_leaving(name, date, photo):
    # Convert date to datetime for MongoDB query
    query_date = datetime.combine(date, datetime.min.time())
    
    entry = attendance_collection.find_one({"Name": name, "Date": query_date})
    if not entry:
        return False, "Arrival not logged for today."

    if entry['Leaving Time'] is not None:
        return False, "Leaving time already logged for today."

    leaving_time = datetime.now()
    arrival_time = datetime.strptime(entry['Arrival Time'], '%I:%M %p')
    # Combine the date and time for both arrival and leaving
    date_obj = datetime.combine(date, datetime.min.time())
    arrival_datetime = date_obj.replace(hour=arrival_time.hour, minute=arrival_time.minute)
    leaving_datetime = date_obj.replace(hour=leaving_time.hour, minute=leaving_time.minute)
    
    # Calculate time difference
    time_diff = leaving_datetime - arrival_datetime
    
    # Handle case where leaving time is on the next day
    if time_diff.total_seconds() < 0:
        leaving_datetime += timedelta(days=1)
        time_diff = leaving_datetime - arrival_datetime
    
    # Calculate hours present
    hours_present = round(time_diff.total_seconds() / 3600, 2)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    photo_data = save_image(photo)

    attendance_collection.update_one(
        {"_id": entry["_id"]},
        {
            "$set": {
                'Leaving Time': leaving_time.strftime('%I:%M %p'),
                'Hours Present': hours_present,
                'Leaving Photo': photo_data
            }
        }
    )
    return True, "Leaving time logged successfully."

def load_attendance():
    entries = list(attendance_collection.find())
    for entry in entries:
        entry['Date'] = entry['Date'].strftime('%Y-%m-%d')
    return pd.DataFrame(entries)

def is_within_allowed_location(lat, lon):
    user_location = (lat, lon)
    distance = geodesic(user_location, ALLOWED_LOCATION).kilometers
    return distance <= MAX_DISTANCE_KM

def calculate_attendance_stats(df, employee, month):
    df['Date'] = pd.to_datetime(df['Date'])
    if month != 'All':
        df = df[df['Date'].dt.strftime('%B %Y') == month]
    
    if employee != 'All':
        df = df[df['Name'] == employee]
    
    stats = []
    for name in df['Name'].unique():
        employee_df = df[df['Name'] == name]
        total_days = len(employee_df)
        total_hours = employee_df['Hours Present'].sum()
        leaves_taken = (employee_df['Arrival Time'].isna() | employee_df['Leaving Time'].isna()).sum()
        
        # Adjust for allowed leave
        if leaves_taken > 1:
            total_days -= (leaves_taken - 1)
            total_hours -= (leaves_taken - 1) * 8
        
        stats.append({
            'Name': name,
            'Total Days Present': total_days,
            'Total Hours': round(total_hours, 2),
            'Leaves Taken': leaves_taken
        })
    
    return pd.DataFrame(stats)

def attendance_stats_page():
    st.title('Attendance Statistics')
    
    df = load_attendance()
    df['Date'] = pd.to_datetime(df['Date'])
    
    employees = ['All'] + list(df['Name'].unique())
    selected_employee = st.selectbox('Select Employee', employees)
    
    months = ['All'] + [d.strftime('%B %Y') for d in pd.date_range(start=df['Date'].min(), end=df['Date'].max(), freq='MS')]
    selected_month = st.selectbox('Select Month', months)
    
    stats_df = calculate_attendance_stats(df, selected_employee, selected_month)
    st.dataframe(stats_df)
    
    # Export as CSV
    csv = stats_df.to_csv(index=False)
    st.download_button(
        label="Download CSV",
        data=csv,
        file_name="attendance_stats.csv",
        mime="text/csv"
    )

def main():
    st.sidebar.title('Navigation')
    page = st.sidebar.radio('Go to', ['Attendance Logging', 'Attendance Statistics'])
    
    if page == 'Attendance Logging':
        attendance_logging_page()
    elif page == 'Attendance Statistics':
        attendance_stats_page()

def attendance_logging_page():
    st.title('Employee Attendance System')

    # Get user's location
    location = get_geolocation()

    if location is None:
        st.warning('Waiting for location data...')
        return

    lat, lon = location['coords']['latitude'], location['coords']['longitude']

    if not is_within_allowed_location(lat, lon):
        st.error('You are not within the allowed location to log your attendance.')
        return

    employees = ['Muzamil Javeed', 'Asim Sumair', 'Arsalan Ahmad', 'Mohammad Unaib', 'Talib Shabir', 'Syed Owais Bashir', 'Ovais Tariq Lone', 'Owais Mir', 'Numair', 'Jehangir', 'Zained Khursheed', 'Tabarak', 'Navreen']
    selected_employee = st.selectbox('Select Employee', employees)

    current_date = date.today()
    
    # Use Streamlit session state to store data
    if 'df' not in st.session_state:
        st.session_state.df = load_attendance()

    # Filter for today's entries for the selected employee
    today_entries = st.session_state.df[(st.session_state.df['Name'] == selected_employee) & (st.session_state.df['Date'] == current_date.strftime('%Y-%m-%d'))]

    if today_entries.empty:
        # No entry for today, show arrival log button and camera input
        st.write("Please take a photo for attendance verification:")
        img_file = st.camera_input("Take a picture")

        if img_file is not None:
            if st.button('Log Arrival Time'):
                success, message = log_arrival(selected_employee, current_date, img_file)
                if success:
                    st.session_state.df = load_attendance()  # Reload the updated dataframe
                    st.success(message)
                    st.experimental_rerun()  # Force Streamlit to rerun the script
                else:
                    st.error(message)
    else:
        # Entry exists for today
        latest_entry = today_entries.iloc[-1]  # Get the latest entry for today
        if pd.isna(latest_entry['Leaving Time']):
            # Arrival logged, but leaving time not logged
            st.info(f"Arrival time logged at: {latest_entry['Arrival Time']}")

            st.write("Please take a photo for attendance verification:")
            img_file = st.camera_input("Take a picture")

            if img_file is not None:
                if st.button('Log Leaving Time'):
                    success, message = log_leaving(selected_employee, current_date, img_file)
                    if success:
                        st.session_state.df = load_attendance()  # Reload the updated dataframe
                        st.success(message)
                        st.experimental_rerun()  # Force Streamlit to rerun the script
                    else:
                        st.error(message)
        else:
            # Both arrival and leaving times are logged
            st.info(f"You have already logged both arrival ({latest_entry['Arrival Time']}) and leaving ({latest_entry['Leaving Time']}) times for today.")

    # Display all employees' attendance records for today without ID, Arrival Photo, and Leaving Photo
    st.write("Current Attendance Records for Today:")
    today_all_entries = st.session_state.df[st.session_state.df['Date'] == current_date.strftime('%Y-%m-%d')]
    if not today_all_entries.empty:
        today_all_entries = today_all_entries.drop(columns=['_id', 'Arrival Photo', 'Leaving Photo'])
    st.dataframe(today_all_entries)

if __name__ == '__main__':
    main()
