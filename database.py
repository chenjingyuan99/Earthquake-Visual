import pyodbc
import pandas as pd
from datetime import datetime, timedelta
import math
import os
from timezonefinder import TimezoneFinder
import pytz

class DatabaseManager:
    def __init__(self):
        # Azure SQL Database connection string

        self.connection_string = (
            f"Driver={{ODBC Driver 18 for SQL Server}};"
            f"Server=tcp:{os.getenv('DB_SERVER')},1433;"
            f"Database={os.getenv('DB_NAME')};"
            f"Uid={os.getenv('DB_USERNAME')};"
            f"Pwd={os.getenv('DB_PASSWORD')};"
            "Encrypt=yes;"
            "TrustServerCertificate=no;"
            "Connection Timeout=30;"
        )
        # Initialize timezone finder
        self.tf = TimezoneFinder()
    
    def get_connection(self):
        """Get database connection"""
        try:
            return pyodbc.connect(self.connection_string)
        except Exception as e:
            print(f"Database connection error: {e}")
            return None
    
    def calculate_local_time_fields(self, utc_time, latitude, longitude):
        """Calculate local time, hour_of_day, and day_of_week based on coordinates"""
        try:
            # Convert to pandas datetime if it's a string
            if isinstance(utc_time, str):
                time_obj = pd.to_datetime(utc_time, utc=True)
            else:
                time_obj = pd.to_datetime(utc_time, utc=True)
            
            # Get timezone name from coordinates
            tz_name = self.tf.timezone_at(lng=float(longitude), lat=float(latitude))
            
            if tz_name:
                # Convert UTC time to local timezone
                local_tz = pytz.timezone(tz_name)
                local_time = time_obj.tz_convert(local_tz)
                
                # Extract hour and day of week from local time
                hour_of_day = local_time.hour
                day_of_week = local_time.weekday() + 1  # Monday=0 -> Monday=1
                
                # Return timezone-naive datetime for database storage
                return local_time.tz_localize(None), hour_of_day, day_of_week
            else:
                # If timezone can't be determined, use UTC
                hour_of_day = time_obj.hour
                day_of_week = time_obj.weekday() + 1
                return time_obj.tz_localize(None), hour_of_day, day_of_week
                
        except Exception as e:
            print(f"Error calculating local time: {e}")
            # Fallback to UTC if calculation fails
            try:
                time_obj = pd.to_datetime(utc_time, utc=True)
                hour_of_day = time_obj.hour
                day_of_week = time_obj.weekday() + 1
                return time_obj.tz_localize(None), hour_of_day, day_of_week
            except:
                return None, None, None

    def create_table_and_upload_data(self, df):
        """Create table and upload data in batches with correct local time calculation"""
        conn = self.get_connection()
        if not conn:
            return False, "Database connection failed"
        
        try:
            cursor = conn.cursor()
            
            # Drop table if exists
            cursor.execute("IF OBJECT_ID('earthquakes_511610', 'U') IS NOT NULL DROP TABLE earthquakes_511610")
            
            # Create table with indexes
            create_table_sql = """
            CREATE TABLE earthquakes_511610 (
                id NVARCHAR(50) PRIMARY KEY,
                time DATETIME2 NOT NULL,
                latitude FLOAT NOT NULL,
                longitude FLOAT NOT NULL,
                depth FLOAT NOT NULL,
                mag FLOAT NOT NULL,
                place NVARCHAR(500) NOT NULL,
                local_time DATETIME2,
                hour_of_day INT,
                day_of_week INT
            );
            
            CREATE INDEX IX_earthquakes_time ON earthquakes_511610(time);
            CREATE INDEX IX_earthquakes_magnitude ON earthquakes_511610(mag);
            CREATE INDEX IX_earthquakes_location ON earthquakes_511610(latitude, longitude);
            CREATE INDEX IX_earthquakes_place ON earthquakes_511610(place);
            CREATE INDEX IX_earthquakes_local_time ON earthquakes_511610(local_time);
            CREATE INDEX IX_earthquakes_hour ON earthquakes_511610(hour_of_day);
            """
            
            cursor.execute(create_table_sql)
            conn.commit()
            
            # Prepare data for insertion
            batch_size = 100
            total_rows = len(df)
            processed_count = 0
            
            print(f"Processing {total_rows} earthquake records with timezone calculations...")

            # Preprocess all local time data to avoid single calculation in loop
            local_times = []
            for _, row in df.iterrows():
                time_obj = pd.to_datetime(row['time'])
                local_time, hour_of_day, day_of_week = self.calculate_local_time_fields(
                    row['time'], row['latitude'], row['longitude']
                )
                local_times.append((
                    str(row['id']),
                    time_obj,
                    float(row['latitude']),
                    float(row['longitude']),
                    float(row['depth']),
                    float(row['mag']),
                    str(row['place']),
                    local_time,
                    hour_of_day,
                    day_of_week
                ))

            print("✅ Finished timezone calculations, start batch inserting...")

            # Batch Insert
            conn = self.get_connection()
            if not conn:
                print("Database connection failed.")
                return False, "Database connection failed"

            try:
                cursor = conn.cursor()
                cursor.fast_executemany = True

                insert_sql = """
                INSERT INTO earthquakes_511610 
                (id, time, latitude, longitude, depth, mag, place, local_time, hour_of_day, day_of_week)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """

                batch_size = 200
                total_rows = len(local_times)

                for i in range(0, total_rows, batch_size):
                    batch = local_times[i:i + batch_size]
                    cursor.executemany(insert_sql, batch)
                    conn.commit()
                    print(f"Inserted {min(i + batch_size, total_rows)} / {total_rows} records...")

                cursor.close()
                conn.close()
                print(f"✅ Successfully uploaded {total_rows} records with timezone-aware local times")
                return True, f"Successfully uploaded {total_rows} records with timezone-aware local times"

            except Exception as e:
                if conn:
                    conn.close()
                print(f"❌ Error uploading data: {e}")
                return False, str(e)

        except Exception as e:
            if conn:
                conn.close()
            print(f"❌ Error uploading data: {e}")
            return False, str(e)
    
    def get_random_earthquake(self):
        """Get a random earthquake record"""
        conn = self.get_connection()
        if not conn:
            return None
        
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT TOP 1 id, time, latitude, longitude, depth, mag, place 
                FROM earthquakes_511610 
                ORDER BY NEWID()
            """)
            
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if row:
                return {
                    'id': row[0],
                    'time': row[1].isoformat() if row[1] else None,
                    'latitude': row[2],
                    'longitude': row[3],
                    'depth': row[4],
                    'magnitude': row[5],
                    'place': row[6]
                }
            return None
            
        except Exception as e:
            if conn:
                conn.close()
            print(f"Error getting random earthquake: {e}")
            return None
    
    def search_by_place(self, place_substring):
        """Search earthquakes by place substring"""
        conn = self.get_connection()
        if not conn:
            return []
        
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, time, latitude, longitude, depth, mag, place 
                FROM earthquakes_511610 
                WHERE place LIKE ?
                ORDER BY time DESC
            """, f'%{place_substring}%')
            
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            results = []
            for row in rows:
                results.append({
                    'id': row[0],
                    'time': row[1].isoformat() if row[1] else None,
                    'latitude': row[2],
                    'longitude': row[3],
                    'depth': row[4],
                    'magnitude': row[5],
                    'place': row[6]
                })
            
            return results
            
        except Exception as e:
            if conn:
                conn.close()
            print(f"Error searching by place: {e}")
            return []
    
    def search_by_location(self, lat, lon, radius_km):
        """Search earthquakes within radius of location"""
        conn = self.get_connection()
        if not conn:
            return []
        
        try:
            cursor = conn.cursor()
            # Using Haversine formula approximation
            cursor.execute("""
                SELECT id, time, latitude, longitude, depth, mag, place,
                       (6371 * ACOS(COS(RADIANS(?)) * COS(RADIANS(latitude)) * 
                        COS(RADIANS(longitude) - RADIANS(?)) + 
                        SIN(RADIANS(?)) * SIN(RADIANS(latitude)))) AS distance
                FROM earthquakes_511610
                WHERE (6371 * ACOS(COS(RADIANS(?)) * COS(RADIANS(latitude)) * 
                       COS(RADIANS(longitude) - RADIANS(?)) + 
                       SIN(RADIANS(?)) * SIN(RADIANS(latitude)))) <= ?
                ORDER BY distance
            """, lat, lon, lat, lat, lon, lat, radius_km)
            
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            results = []
            for row in rows:
                results.append({
                    'id': row[0],
                    'time': row[1].isoformat() if row[1] else None,
                    'latitude': row[2],
                    'longitude': row[3],
                    'depth': row[4],
                    'magnitude': row[5],
                    'place': row[6],
                    'distance_km': round(row[7], 2)
                })
            
            return results
            
        except Exception as e:
            if conn:
                conn.close()
            print(f"Error searching by location: {e}")
            return []
    
    def search_by_time_range(self, start_date, end_date):
        """Search earthquakes within time range"""
        conn = self.get_connection()
        if not conn:
            return []
        
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, time, latitude, longitude, depth, mag, place 
                FROM earthquakes_511610 
                WHERE time BETWEEN ? AND ?
                ORDER BY time DESC
            """, start_date, end_date)
            
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            results = []
            for row in rows:
                results.append({
                    'id': row[0],
                    'time': row[1].isoformat() if row[1] else None,
                    'latitude': row[2],
                    'longitude': row[3],
                    'depth': row[4],
                    'magnitude': row[5],
                    'place': row[6]
                })
            
            return results
            
        except Exception as e:
            if conn:
                conn.close()
            print(f"Error searching by time range: {e}")
            return []
    
    def search_by_magnitude(self, min_mag, max_mag):
        """Search earthquakes within magnitude range"""
        conn = self.get_connection()
        if not conn:
            return []
        
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, time, latitude, longitude, depth, mag, place 
                FROM earthquakes_511610 
                WHERE mag BETWEEN ? AND ?
                ORDER BY mag DESC
            """, min_mag, max_mag)
            
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            results = []
            for row in rows:
                results.append({
                    'id': row[0],
                    'time': row[1].isoformat() if row[1] else None,
                    'latitude': row[2],
                    'longitude': row[3],
                    'depth': row[4],
                    'magnitude': row[5],
                    'place': row[6]
                })
            
            return results
            
        except Exception as e:
            if conn:
                conn.close()
            print(f"Error searching by magnitude: {e}")
            return []
        
    # Visualize
    def get_magnitude_distribution(self):
        """Get earthquake count by magnitude ranges"""
        conn = self.get_connection()
        if not conn:
            return {}
        
        try:
            cursor = conn.cursor()
            intervals = [(0,1), (1,2), (2,3), (3,4), (4,5)]
            results = {}
            
            for low, high in intervals:
                cursor.execute("""
                    SELECT COUNT(*) FROM earthquakes_511610 
                    WHERE mag >= ? AND mag < ?
                """, low, high)
                count = cursor.fetchone()[0]
                results[f'{low}-{high}'] = count
            
            # Count for 5+
            cursor.execute("SELECT COUNT(*) FROM earthquakes_511610 WHERE mag >= 5")
            count_5plus = cursor.fetchone()[0]
            results['5+'] = count_5plus
            
            cursor.close()
            conn.close()
            return results
            
        except Exception as e:
            if conn:
                conn.close()
            print(f"Error getting magnitude distribution: {e}")
            return {}

    def get_recent_magnitude_depth(self, limit=100):
        """Get magnitude vs depth for recent earthquakes"""
        conn = self.get_connection()
        if not conn:
            return []
        
        try:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT TOP {limit} mag, depth, time, place 
                FROM earthquakes_511610 
                ORDER BY time DESC
            """)
            
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            results = []
            for row in rows:
                results.append({
                    'magnitude': float(row[0]) if row[0] else 0,
                    'depth': float(row[1]) if row[1] else 0,
                    'time': row[2].isoformat() if row[2] else None,
                    'place': row[3] if row[3] else ''
                })
            
            return results
            
        except Exception as e:
            if conn:
                conn.close()
            print(f"Error getting magnitude vs depth: {e}")
            return []

    def get_hourly_distribution(self):
        """Get earthquake count by hour of day"""
        conn = self.get_connection()
        if not conn:
            return {}
        
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT hour_of_day, COUNT(*) as count
                FROM earthquakes_511610 
                WHERE hour_of_day IS NOT NULL
                GROUP BY hour_of_day
                ORDER BY hour_of_day
            """)
            
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            results = {}
            for row in rows:
                results[str(row[0])] = row[1]
            
            return results
            
        except Exception as e:
            if conn:
                conn.close()
            print(f"Error getting hourly distribution: {e}")
            return {}

    def get_hourly_distribution_filtered(self, min_magnitude=0):
        """Get earthquake count by hour of day filtered by minimum magnitude"""
        conn = self.get_connection()
        if not conn:
            return {}
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT hour_of_day, COUNT(*) as count
                FROM earthquakes_511610 
                WHERE hour_of_day IS NOT NULL AND mag >= ?
                GROUP BY hour_of_day
                ORDER BY hour_of_day
            """, min_magnitude)
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            results = {}
            # Ensure all 24 hours are represented
            for hour in range(24):
                results[str(hour)] = 0
            for row in rows:
                results[str(row[0])] = row[1]
            return results
        except Exception as e:
            if conn:
                conn.close()
            print(f"Error getting hourly distribution filtered: {e}")
            return {}

    def get_depth_distribution(self):
        """Get earthquake count by depth ranges"""
        conn = self.get_connection()
        if not conn:
            return {}
        
        try:
            cursor = conn.cursor()
            depth_ranges = [
                (0, 10, "0-10km"),
                (10, 50, "10-50km"),
                (50, 100, "50-100km"),
                (100, 300, "100-300km"),
                (300, 1000, "300km+")
            ]
            
            results = {}
            for min_depth, max_depth, label in depth_ranges:
                if label == "300km+":
                    cursor.execute("""
                        SELECT COUNT(*) FROM earthquakes_511610 
                        WHERE depth >= ?
                    """, min_depth)
                else:
                    cursor.execute("""
                        SELECT COUNT(*) FROM earthquakes_511610 
                        WHERE depth >= ? AND depth < ?
                    """, min_depth, max_depth)
                
                count = cursor.fetchone()[0]
                results[label] = count
            
            cursor.close()
            conn.close()
            return results
            
        except Exception as e:
            if conn:
                conn.close()
            print(f"Error getting depth distribution: {e}")
            return {}

    def get_top_locations(self, limit=10):
        """Get top earthquake locations by count"""
        conn = self.get_connection()
        if not conn:
            return []
        
        try:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT TOP {limit} 
                    CASE 
                        WHEN CHARINDEX(',', place) > 0 
                        THEN LTRIM(RTRIM(SUBSTRING(place, CHARINDEX(',', place) + 1, LEN(place))))
                        ELSE place 
                    END as location,
                    COUNT(*) as count
                FROM earthquakes_511610 
                WHERE place IS NOT NULL
                GROUP BY 
                    CASE 
                        WHEN CHARINDEX(',', place) > 0 
                        THEN LTRIM(RTRIM(SUBSTRING(place, CHARINDEX(',', place) + 1, LEN(place))))
                        ELSE place 
                    END
                ORDER BY COUNT(*) DESC
            """)
            
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            results = []
            for row in rows:
                results.append({
                    'location': row[0],
                    'count': row[1]
                })
            
            return results
            
        except Exception as e:
            if conn:
                conn.close()
            print(f"Error getting top locations: {e}")
            return []

    def get_earthquakes_past_30_days(self, min_magnitude=None):
        """Get earthquakes from the past 30 days for map visualization"""
        conn = self.get_connection()
        if not conn:
            return []
        
        try:
            cursor = conn.cursor()
            
            if min_magnitude is not None:
                cursor.execute("""
                    SELECT id, time, latitude, longitude, depth, mag, place 
                    FROM earthquakes_511610 
                    WHERE mag >= ?
                    ORDER BY time DESC
                """, min_magnitude)
            else:
                cursor.execute("""
                    SELECT id, time, latitude, longitude, depth, mag, place 
                    FROM earthquakes_511610 
                    ORDER BY time DESC
                """)
            
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            results = []
            for row in rows:
                results.append({
                    'id': row[0],
                    'time': row[1].isoformat() if row[1] else None,
                    'latitude': float(row[2]) if row[2] else 0,
                    'longitude': float(row[3]) if row[3] else 0,
                    'depth': float(row[4]) if row[4] else 0,
                    'magnitude': float(row[5]) if row[5] else 0,
                    'place': row[6] if row[6] else ''
                })
            
            return results
            
        except Exception as e:
            if conn:
                conn.close()
            print(f"Error getting earthquakes past 30 days: {e}")
            return []
