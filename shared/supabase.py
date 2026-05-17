import os
from supabase import create_client

SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://qmgbtcuxmlhnfodqcudf.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFtZ2J0Y3V4bWxobmZvZHFjdWRmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg5NjUzNTcsImV4cCI6MjA5NDU0MTM1N30.b3o4_hd0e41bUTYYXGZ-yddCfhccmsJGwf106M1wlLA')
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
