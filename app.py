"""
Earthquake Data Analysis Web Application Based on Redis/SQL server/blob
Author: Jingyuan Chen 9629
Course: CSE 6332 Cloud Computing
"""

from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
import pandas as pd
import os
import time
from datetime import datetime
import json
from database import DatabaseManager
from redis_cache import RedisCache
from werkzeug.utils import secure_filename
import random
import math

app = Flask(__name__)
app.secret_key = 'earth2025'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Initialize components
db_manager = DatabaseManager()
redis_cache = RedisCache()

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')

# progress bar
@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    """Handle CSV file upload and processing with progress tracking"""
    if request.method == 'GET':
        return render_template('upload.html')
    
    if 'file' not in request.files:
        flash('No file selected')
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected')
        return redirect(request.url)
    
    if file and file.filename.lower().endswith('.csv'):
        try:
            # Read and clean CSV data
            print("📖 Reading CSV file...")
            df = pd.read_csv(file)
            
            print("🧹 Cleaning data...")
            # Clean data - remove rows with null values in critical columns
            critical_columns = ['time', 'latitude', 'longitude', 'depth', 'mag', 'place']
            initial_count = len(df)
            df_cleaned = df.dropna(subset=critical_columns)
            
            # Select only required columns
            required_columns = ['id', 'time', 'latitude', 'longitude', 'depth', 'mag', 'place']
            df_final = df_cleaned[required_columns].copy()
            
            cleaned_count = len(df_final)
            print(f"📊 Data cleaned: {initial_count} -> {cleaned_count} records")
            
            # Process data and upload to database
            print("🔄 Starting database upload with timezone calculations...")
            start_time = time.time()
            success, message = db_manager.create_table_and_upload_data(df_final)
            end_time = time.time()
            
            processing_time = round(end_time - start_time, 2)
            
            if success:
                # Save cleaned data to blob storage
                print("💾 Saving cleaned data...")
                cleaned_filename = f"cleaned_earthquake_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                df_final.to_csv(cleaned_filename, index=False)
                
                flash(f'Successfully uploaded {cleaned_count} records to database in {processing_time} seconds')
                return render_template('upload.html', 
                                     success=True, 
                                     records_count=cleaned_count,
                                     processing_time=processing_time)
            else:
                flash(f'Error uploading data: {message}')
                return render_template('upload.html', error=message)
                
        except Exception as e:
            print(f"❌ Upload error: {e}")
            flash(f'Error processing file: {str(e)}')
            return render_template('upload.html', error=str(e))
    
    flash('Please upload a valid CSV file')
    return redirect(request.url)

@app.route('/query')
def query_page():
    """Query interface page"""
    return render_template('query.html')

@app.route('/api/random_queries', methods=['POST'])
def random_queries():
    """Execute random queries"""
    data = request.get_json()
    num_queries = min(int(data.get('num_queries', 10)), 1000)
    use_redis = data.get('use_redis', False)
    
    start_time = time.time()
    results = []
    cache_hits = 0
    
    for i in range(num_queries):
        if use_redis:
            cache_key = f"random_query_{random.randint(1, 10000)}"
            cached_result = redis_cache.get(cache_key)
            
            if cached_result:
                results.append(cached_result)
                cache_hits += 1
            else:
                result = db_manager.get_random_earthquake()
                if result:
                    redis_cache.set(cache_key, result, expire_time=300)  # 5 minutes
                    results.append(result)
        else:
            result = db_manager.get_random_earthquake()
            if result:
                results.append(result)
    
    end_time = time.time()
    execution_time = round(end_time - start_time, 3)
    hit_rate = round((cache_hits / num_queries) * 100, 2) if use_redis else 0
    
    return jsonify({
        'results': results,
        'execution_time': execution_time,
        'cache_hits': cache_hits,
        'hit_rate': hit_rate,
        'total_queries': num_queries
    })

@app.route('/api/place_search', methods=['POST'])
def place_search():
    """Search earthquakes by place substring"""
    data = request.get_json()
    place_substring = data.get('place_substring', '')
    use_redis = data.get('use_redis', False)
    
    cache_key = f"place_search_{place_substring.lower()}"
    start_time = time.time()
    
    if use_redis:
        cached_result = redis_cache.get(cache_key)
        if cached_result:
            end_time = time.time()
            return jsonify({
                'results': cached_result,
                'execution_time': round(end_time - start_time, 3),
                'cache_hit': True,
                'hit_rate': 100.0
            })
    
    results = db_manager.search_by_place(place_substring)
    end_time = time.time()
    
    if use_redis and results:
        redis_cache.set(cache_key, results, expire_time=600)  # 10 minutes
    
    return jsonify({
        'results': results,
        'execution_time': round(end_time - start_time, 3),
        'cache_hit': False,
        'hit_rate': 0.0
    })

@app.route('/api/location_search', methods=['POST'])
def location_search():
    """Search earthquakes within N km of specified location"""
    data = request.get_json()
    lat = float(data.get('latitude', 0))
    lon = float(data.get('longitude', 0))
    radius_km = min(float(data.get('radius_km', 50)), 100)
    use_redis = data.get('use_redis', False)
    
    cache_key = f"location_search_{lat}_{lon}_{radius_km}"
    start_time = time.time()
    
    if use_redis:
        cached_result = redis_cache.get(cache_key)
        if cached_result:
            end_time = time.time()
            return jsonify({
                'results': cached_result,
                'execution_time': round(end_time - start_time, 3),
                'cache_hit': True,
                'hit_rate': 100.0
            })
    
    results = db_manager.search_by_location(lat, lon, radius_km)
    end_time = time.time()
    
    if use_redis and results:
        redis_cache.set(cache_key, results, expire_time=600)
    
    return jsonify({
        'results': results,
        'execution_time': round(end_time - start_time, 3),
        'cache_hit': False,
        'hit_rate': 0.0
    })

@app.route('/api/time_range_search', methods=['POST'])
def time_range_search():
    """Search earthquakes within time range"""
    data = request.get_json()
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    use_redis = data.get('use_redis', False)
    
    cache_key = f"time_range_{start_date}_{end_date}"
    start_time = time.time()
    
    if use_redis:
        cached_result = redis_cache.get(cache_key)
        if cached_result:
            end_time = time.time()
            return jsonify({
                'results': cached_result,
                'execution_time': round(end_time - start_time, 3),
                'cache_hit': True,
                'hit_rate': 100.0
            })
    
    results = db_manager.search_by_time_range(start_date, end_date)
    end_time = time.time()
    
    if use_redis and results:
        redis_cache.set(cache_key, results, expire_time=600)
    
    return jsonify({
        'results': results,
        'execution_time': round(end_time - start_time, 3),
        'cache_hit': False,
        'hit_rate': 0.0
    })

@app.route('/api/magnitude_search', methods=['POST'])
def magnitude_search():
    """Search earthquakes within magnitude range"""
    data = request.get_json()
    min_mag = float(data.get('min_magnitude', 0))
    max_mag = float(data.get('max_magnitude', 10))
    use_redis = data.get('use_redis', False)
    
    cache_key = f"magnitude_{min_mag}_{max_mag}"
    start_time = time.time()
    
    if use_redis:
        cached_result = redis_cache.get(cache_key)
        if cached_result:
            end_time = time.time()
            return jsonify({
                'results': cached_result,
                'execution_time': round(end_time - start_time, 3),
                'cache_hit': True,
                'hit_rate': 100.0
            })
    
    results = db_manager.search_by_magnitude(min_mag, max_mag)
    end_time = time.time()
    
    if use_redis and results:
        redis_cache.set(cache_key, results, expire_time=600)
    
    return jsonify({
        'results': results,
        'execution_time': round(end_time - start_time, 3),
        'cache_hit': False,
        'hit_rate': 0.0
    })

# At the top of app.py, replace redis import
from memory_cache import MemoryCache

# Replace redis_cache initialization
memory_cache = MemoryCache()

# Add a test endpoint
@app.route('/api/cache_test')
def cache_test():
    """Test cache functionality"""
    # Test set
    test_data = {"test": "data", "timestamp": time.time()}
    memory_cache.set("test_key", test_data, 60)
    
    # Test get
    retrieved = memory_cache.get("test_key")
    
    stats = memory_cache.get_stats()
    
    return jsonify({
        'set_data': test_data,
        'retrieved_data': retrieved,
        'cache_working': retrieved is not None,
        'cache_stats': stats
    })

# visualize
@app.route('/visualize')
def visualize_page():
    """Data visualization page"""
    return render_template('visualize.html')

@app.route('/api/magnitude_distribution')
def api_magnitude_distribution():
    """API endpoint for magnitude distribution data"""
    use_redis = request.args.get('use_redis', 'false').lower() == 'true'
    cache_key = "magnitude_distribution"
    
    start_time = time.time()
    
    if use_redis:
        cached_result = redis_cache.get(cache_key)
        if cached_result:
            end_time = time.time()
            return jsonify({
                'data': cached_result,
                'execution_time': round(end_time - start_time, 3),
                'cache_hit': True
            })
    
    data = db_manager.get_magnitude_distribution()
    end_time = time.time()
    
    if use_redis and data:
        redis_cache.set(cache_key, data, expire_time=1800)  # 30 minutes
    
    return jsonify({
        'data': data,
        'execution_time': round(end_time - start_time, 3),
        'cache_hit': False
    })

@app.route('/api/magnitude_depth_scatter')
def api_magnitude_depth_scatter():
    """API endpoint for magnitude vs depth scatter plot data"""
    limit = min(int(request.args.get('limit', 100)), 500)
    use_redis = request.args.get('use_redis', 'false').lower() == 'true'
    cache_key = f"magnitude_depth_scatter_{limit}"
    
    start_time = time.time()
    
    if use_redis:
        cached_result = redis_cache.get(cache_key)
        if cached_result:
            end_time = time.time()
            return jsonify({
                'data': cached_result,
                'execution_time': round(end_time - start_time, 3),
                'cache_hit': True
            })
    
    data = db_manager.get_recent_magnitude_depth(limit)
    end_time = time.time()
    
    if use_redis and data:
        redis_cache.set(cache_key, data, expire_time=900)  # 15 minutes
    
    return jsonify({
        'data': data,
        'execution_time': round(end_time - start_time, 3),
        'cache_hit': False
    })

@app.route('/api/hourly_distribution')
def api_hourly_distribution():
    """API endpoint for hourly distribution data"""
    use_redis = request.args.get('use_redis', 'false').lower() == 'true'
    cache_key = "hourly_distribution"
    
    start_time = time.time()
    
    if use_redis:
        cached_result = redis_cache.get(cache_key)
        if cached_result:
            end_time = time.time()
            return jsonify({
                'data': cached_result,
                'execution_time': round(end_time - start_time, 3),
                'cache_hit': True
            })
    
    data = db_manager.get_hourly_distribution()
    end_time = time.time()
    
    if use_redis and data:
        redis_cache.set(cache_key, data, expire_time=1800)
    
    return jsonify({
        'data': data,
        'execution_time': round(end_time - start_time, 3),
        'cache_hit': False
    })

@app.route('/api/hourly_distribution_filtered')
def api_hourly_distribution_filtered():
    min_magnitude = float(request.args.get('min_magnitude', 4))
    use_redis = request.args.get('use_redis', 'false').lower() == 'true'
    cache_key = f"hourly_distribution_filtered_{min_magnitude}"
    start_time = time.time()
    if use_redis:
        cached_result = redis_cache.get(cache_key)
        if cached_result:
            end_time = time.time()
            return jsonify({
                'data': cached_result,
                'execution_time': round(end_time - start_time, 3),
                'cache_hit': True
            })
    data = db_manager.get_hourly_distribution_filtered(min_magnitude)
    end_time = time.time()
    if use_redis and data:
        redis_cache.set(cache_key, data, expire_time=1800)
    return jsonify({
        'data': data,
        'execution_time': round(end_time - start_time, 3),
        'cache_hit': False
    })

@app.route('/api/depth_distribution')
def api_depth_distribution():
    """API endpoint for depth distribution data"""
    use_redis = request.args.get('use_redis', 'false').lower() == 'true'
    cache_key = "depth_distribution"
    
    start_time = time.time()
    
    if use_redis:
        cached_result = redis_cache.get(cache_key)
        if cached_result:
            end_time = time.time()
            return jsonify({
                'data': cached_result,
                'execution_time': round(end_time - start_time, 3),
                'cache_hit': True
            })
    
    data = db_manager.get_depth_distribution()
    end_time = time.time()
    
    if use_redis and data:
        redis_cache.set(cache_key, data, expire_time=1800)
    
    return jsonify({
        'data': data,
        'execution_time': round(end_time - start_time, 3),
        'cache_hit': False
    })

@app.route('/api/top_locations')
def api_top_locations():
    """API endpoint for top earthquake locations"""
    limit = min(int(request.args.get('limit', 10)), 20)
    use_redis = request.args.get('use_redis', 'false').lower() == 'true'
    cache_key = f"top_locations_{limit}"
    
    start_time = time.time()
    
    if use_redis:
        cached_result = redis_cache.get(cache_key)
        if cached_result:
            end_time = time.time()
            return jsonify({
                'data': cached_result,
                'execution_time': round(end_time - start_time, 3),
                'cache_hit': True
            })
    
    data = db_manager.get_top_locations(limit)
    end_time = time.time()
    
    if use_redis and data:
        redis_cache.set(cache_key, data, expire_time=1800)
    
    return jsonify({
        'data': data,
        'execution_time': round(end_time - start_time, 3),
        'cache_hit': False
    })

@app.route('/api/earthquakes_map')
def api_earthquakes_map():
    """API endpoint for earthquake map data"""
    min_magnitude = request.args.get('min_magnitude', type=float)
    use_redis = request.args.get('use_redis', 'false').lower() == 'true'
    
    cache_key = f"earthquakes_map_{min_magnitude if min_magnitude else 'all'}"
    
    start_time = time.time()
    
    if use_redis:
        cached_result = redis_cache.get(cache_key)
        if cached_result:
            end_time = time.time()
            return jsonify({
                'data': cached_result,
                'execution_time': round(end_time - start_time, 3),
                'cache_hit': True,
                'count': len(cached_result)
            })
    
    data = db_manager.get_earthquakes_past_30_days(min_magnitude)
    end_time = time.time()
    
    if use_redis and data:
        redis_cache.set(cache_key, data, expire_time=1800)  # 30 minutes
    
    return jsonify({
        'data': data,
        'execution_time': round(end_time - start_time, 3),
        'cache_hit': False,
        'count': len(data)
    })

if __name__ == '__main__':
    app.run(debug=True, port=5678)
