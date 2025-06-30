# Create a new file: memory_cache.py
import time
import json

class MemoryCache:
    def __init__(self):
        self.cache = {}
        self.timestamps = {}
        print("✅ Memory cache initialized")
    
    def set(self, key, value, expire_time=3600):
        """Set value in memory cache"""
        try:
            normalized_key = key.lower().strip()
            self.cache[normalized_key] = value
            self.timestamps[normalized_key] = time.time() + expire_time
            print(f"✅ MEMORY CACHE SET: {normalized_key}")
            return True
        except Exception as e:
            print(f"❌ Memory cache SET error: {e}")
            return False
    
    def get(self, key):
        """Get value from memory cache"""
        try:
            normalized_key = key.lower().strip()
            
            # Check if key exists and not expired
            if normalized_key in self.cache:
                if time.time() < self.timestamps[normalized_key]:
                    print(f"🎯 MEMORY CACHE HIT: {normalized_key}")
                    return self.cache[normalized_key]
                else:
                    # Remove expired entry
                    del self.cache[normalized_key]
                    del self.timestamps[normalized_key]
                    print(f"⏰ MEMORY CACHE EXPIRED: {normalized_key}")
            
            print(f"❌ MEMORY CACHE MISS: {normalized_key}")
            return None
        except Exception as e:
            print(f"❌ Memory cache GET error: {e}")
            return None
    
    def clear_all(self):
        """Clear all cache"""
        self.cache.clear()
        self.timestamps.clear()
        print("🗑️ Memory cache cleared")
    
    def get_stats(self):
        """Get cache statistics"""
        return {
            'total_keys': len(self.cache),
            'keys': list(self.cache.keys())
        }
