import redis
import json
import os
from datetime import timedelta

class RedisCache:
    def __init__(self):
        # Azure Redis Cache connection
        
        self.redis_host = os.getenv('REDIS_HOST')
        self.redis_port = 6380
        self.redis_password = os.getenv('REDIS_PASSWORD')

        try:
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                password=self.redis_password,
                ssl=True,
                decode_responses=True
            )

            # Test connection
            self.redis_client.ping()
            print("Redis connection successful")
        except Exception as e:
            print(f"Redis connection failed: {e}")
            self.redis_client = None
    
    # def set(self, key, value, expire_time=300):
    #     """Set value in cache with expiration time (seconds)"""
    #     if not self.redis_client:
    #         return False
        
    #     try:
    #         serialized_value = json.dumps(value)
    #         return self.redis_client.setex(key, expire_time, serialized_value)
    #     except Exception as e:
    #         print(f"Redis set error: {e}")
    #         return False
    
    # def get(self, key):
    #     """Get value from cache"""
    #     if not self.redis_client:
    #         return None
        
    #     try:
    #         value = self.redis_client.get(key)
    #         if value:
    #             return json.loads(value)
    #         return None
    #     except Exception as e:
    #         print(f"Redis get error: {e}")
    #         return None
    
    def get(self, key):
        if not self.redis_client:
            print("Redis client not available")
            return None
        
        try:
            value = self.redis_client.get(key)
            if value:
                print(f"Cache HIT for key: {key}")
                return json.loads(value)
            else:
                print(f"Cache MISS for key: {key}")
            return None
        except Exception as e:
            print(f"Redis get error: {e}")
            return None

    def set(self, key, value, expire_time=300):
        if not self.redis_client:
            print("Redis client not available")
            return False
        
        try:
            serialized_value = json.dumps(value)
            result = self.redis_client.setex(key, expire_time, serialized_value)
            print(f"Cache SET for key: {key}, success: {result}")
            return result
        except Exception as e:
            print(f"Redis set error: {e}")
            return False

    def delete(self, key):
        """Delete key from cache"""
        if not self.redis_client:
            return False
        
        try:
            return self.redis_client.delete(key)
        except Exception as e:
            print(f"Redis delete error: {e}")
            return False
    
    def clear_all(self):
        """Clear all cache"""
        if not self.redis_client:
            return False
        
        try:
            return self.redis_client.flushall()
        except Exception as e:
            print(f"Redis clear error: {e}")
            return False
