

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


CREATE EXTENSION IF NOT EXISTS "pg_cron" WITH SCHEMA "pg_catalog";






COMMENT ON SCHEMA "public" IS 'This schema implements a comprehensive role-based access control system with the following principles:
1. Users can always access their own data
2. Team leaders can access data for their team members
3. Admins can access data for teams they administer
4. No user can access data that does not belong to them or their scope of responsibility';



CREATE EXTENSION IF NOT EXISTS "pg_graphql" WITH SCHEMA "graphql";






CREATE EXTENSION IF NOT EXISTS "pg_stat_statements" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pgjwt" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "supabase_vault" WITH SCHEMA "vault";






CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA "extensions";






CREATE OR REPLACE FUNCTION "public"."aggregate_hourly_metrics"() RETURNS "void"
    LANGUAGE "plpgsql"
    AS $$
DECLARE
    current_hour TIMESTAMP WITH TIME ZONE;
BEGIN
    current_hour := DATE_TRUNC('hour', NOW() - INTERVAL '1 hour');
    
    INSERT INTO security_metrics_hourly (
        hour_bucket,
        total_requests,
        unique_ips,
        blocked_requests,
        safe_requests,
        low_threat_requests,
        medium_threat_requests,
        high_threat_requests,
        critical_threat_requests,
        avg_response_time,
        p95_response_time,
        top_countries,
        top_attack_vectors,
        top_threat_ips
    )
    SELECT 
        current_hour,
        COUNT(*),
        COUNT(DISTINCT ip_address),
        COUNT(*) FILTER (WHERE blocked = true),
        COUNT(*) FILTER (WHERE threat_level = 'safe'),
        COUNT(*) FILTER (WHERE threat_level = 'low'),
        COUNT(*) FILTER (WHERE threat_level = 'medium'),
        COUNT(*) FILTER (WHERE threat_level = 'high'),
        COUNT(*) FILTER (WHERE threat_level = 'critical'),
        AVG(response_time_ms),
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY response_time_ms),
        (SELECT jsonb_object_agg(country, cnt) FROM (
            SELECT country, COUNT(*) as cnt 
            FROM security_request_logs 
            WHERE created_at >= current_hour AND created_at < current_hour + INTERVAL '1 hour'
                AND country IS NOT NULL
            GROUP BY country 
            ORDER BY cnt DESC 
            LIMIT 10
        ) t),
        (SELECT jsonb_object_agg(vector, cnt) FROM (
            SELECT unnest(threat_categories) as vector, COUNT(*) as cnt
            FROM security_request_logs 
            WHERE created_at >= current_hour AND created_at < current_hour + INTERVAL '1 hour'
                AND threat_categories IS NOT NULL
            GROUP BY vector 
            ORDER BY cnt DESC 
            LIMIT 10
        ) t),
        (SELECT jsonb_object_agg(ip_address::TEXT, cnt) FROM (
            SELECT ip_address, COUNT(*) as cnt
            FROM security_request_logs 
            WHERE created_at >= current_hour AND created_at < current_hour + INTERVAL '1 hour'
                AND threat_level IN ('high', 'critical')
            GROUP BY ip_address 
            ORDER BY cnt DESC 
            LIMIT 10
        ) t)
    FROM security_request_logs 
    WHERE created_at >= current_hour AND created_at < current_hour + INTERVAL '1 hour'
    ON CONFLICT (hour_bucket) DO NOTHING;
END;
$$;


ALTER FUNCTION "public"."aggregate_hourly_metrics"() OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."users" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "email" "text",
    "full_name" "text" NOT NULL,
    "id_number" "text" NOT NULL,
    "id_front_url" "text" NOT NULL,
    "id_back_url" "text" NOT NULL,
    "phone_number" "text",
    "mobigo_number" "text",
    "role" "text" NOT NULL,
    "team_id" "uuid",
    "staff_type" "text",
    "is_active" boolean DEFAULT true,
    "last_login_at" timestamp with time zone,
    "auth_user_id" "uuid" NOT NULL,
    "status" "text" DEFAULT 'ACTIVE'::"text",
    "admin_id" "uuid",
    "updated_at" timestamp with time zone DEFAULT ("now"() AT TIME ZONE 'utc'::"text") NOT NULL,
    "username" "text",
    "is_first_login" boolean DEFAULT false NOT NULL,
    "password" character varying,
    "soft_delete" boolean DEFAULT false,
    "deleted" boolean DEFAULT false NOT NULL
);


ALTER TABLE "public"."users" OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."bypass_rls_get_user"("user_auth_id" "uuid") RETURNS "public"."users"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
DECLARE
  result users;
BEGIN
  -- This function runs with SECURITY DEFINER and can bypass RLS
  SELECT * INTO result FROM users WHERE auth_user_id = user_auth_id;
  RETURN result;
END;
$$;


ALTER FUNCTION "public"."bypass_rls_get_user"("user_auth_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."calculate_risk_score"("threat_level" character varying, "signature_matches" "text"[], "behavioral_flags" "text"[], "anomaly_score" numeric, "ip_reputation" integer DEFAULT 50) RETURNS integer
    LANGUAGE "plpgsql"
    AS $$
DECLARE
    base_score INTEGER := 0;
    final_score INTEGER := 0;
BEGIN
    -- Base score from threat level
    CASE threat_level
        WHEN 'safe' THEN base_score := 0;
        WHEN 'low' THEN base_score := 20;
        WHEN 'medium' THEN base_score := 50;
        WHEN 'high' THEN base_score := 80;
        WHEN 'critical' THEN base_score := 100;
        ELSE base_score := 0;
    END CASE;
    
    -- Adjust for signature matches
    base_score := base_score + (array_length(signature_matches, 1) * 5);
    
    -- Adjust for behavioral flags
    base_score := base_score + (array_length(behavioral_flags, 1) * 3);
    
    -- Adjust for anomaly score
    base_score := base_score + (anomaly_score * 20)::INTEGER;
    
    -- Factor in IP reputation (lower reputation = higher risk)
    final_score := base_score + ((100 - ip_reputation) / 2);
    
    -- Cap at 100
    RETURN LEAST(final_score, 100);
END;
$$;


ALTER FUNCTION "public"."calculate_risk_score"("threat_level" character varying, "signature_matches" "text"[], "behavioral_flags" "text"[], "anomaly_score" numeric, "ip_reputation" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."cleanup_expired_sessions"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
  -- Delete expired sessions
  DELETE FROM user_sessions
  WHERE expires_at < NOW();
  
  -- Update active sessions count for affected users
  UPDATE user_security_activity
  SET active_sessions = (
    SELECT COUNT(*) FROM user_sessions 
    WHERE user_id = user_security_activity.user_id
  );
  
  RETURN NULL;
END;
$$;


ALTER FUNCTION "public"."cleanup_expired_sessions"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."delete_batch_metadata_on_sim_delete"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
DECLARE
  remaining_count INTEGER;
BEGIN
  -- Check if there are any remaining SIM cards with this batch_id
  SELECT COUNT(*) INTO remaining_count
  FROM sim_cards
  WHERE batch_id = OLD.batch_id;
  
  -- If this was the last SIM card with this batch_id, delete the batch metadata
  IF remaining_count = 0 THEN
    DELETE FROM batch_metadata
    WHERE batch_id = OLD.batch_id;
  END IF;
  
  RETURN OLD;
END;
$$;


ALTER FUNCTION "public"."delete_batch_metadata_on_sim_delete"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."delete_team_with_dependencies"("team_id_param" "uuid") RETURNS "void"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    -- Note: team_performance and staff_performance are views, not tables,
    -- so we don't need to delete from them explicitly

    -- Update users to remove team association
    UPDATE users SET team_id = NULL WHERE team_id = team_id_param;

    -- Delete SIM cards associated with the team
    DELETE FROM sim_cards WHERE team_id = team_id_param;

    -- Delete batch metadata associated with the team
    DELETE FROM batch_metadata WHERE team_id = team_id_param;

    -- Update onboarding requests to remove team association
    UPDATE onboarding_requests SET team_id = NULL WHERE team_id = team_id_param;

    -- Delete any activity logs related to the team (if applicable)
    -- This is optional and depends on your data retention policy
    -- DELETE FROM activity_logs WHERE details->>'team_id' = team_id_param::text;

    -- Finally, delete the team itself
    DELETE FROM teams WHERE id = team_id_param;
END;
$$;


ALTER FUNCTION "public"."delete_team_with_dependencies"("team_id_param" "uuid") OWNER TO "postgres";


CREATE PROCEDURE "public"."delete_user_and_dependants"(IN "target_user_id" "uuid")
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  -- STEP 1: Create temporary table for all users managed by this user
  CREATE TEMP TABLE managed_users AS
  SELECT id FROM users WHERE admin_id = target_user_id;

  -- STEP 2: Delete data belonging to managed users
  DELETE FROM forum_likes WHERE user_id IN (SELECT id FROM managed_users);
  DELETE FROM forum_posts WHERE created_by IN (SELECT id FROM managed_users);
  DELETE FROM forum_topics WHERE created_by IN (SELECT id FROM managed_users);

  DELETE FROM onboarding_requests 
  WHERE requested_by_id IN (SELECT id FROM managed_users)
     OR reviewed_by_id IN (SELECT id FROM managed_users);

  DELETE FROM sim_cards
  WHERE assigned_to_user_id IN (SELECT id FROM managed_users)
     OR sold_by_user_id IN (SELECT id FROM managed_users)
     OR registered_by_user_id IN (SELECT id FROM managed_users);

  DELETE FROM payment_requests WHERE user_id IN (SELECT id FROM managed_users);
  DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM managed_users);
  DELETE FROM activity_logs WHERE user_id IN (SELECT id FROM managed_users);

  -- STEP 3: Nullify team references for managed users
  UPDATE users
  SET team_id = NULL
  WHERE id IN (SELECT id FROM managed_users);

  -- STEP 4: Delete managed users
  DELETE FROM users WHERE id IN (SELECT id FROM managed_users);

  -- STEP 5: Nullify team_id for users linked to teams created by the target user
  UPDATE users
  SET team_id = NULL
  WHERE team_id IN (
    SELECT id FROM teams
    WHERE admin_id = target_user_id OR leader_id = target_user_id
  );

  -- STEP 6: Delete teams created/led by target user
  DELETE FROM teams
  WHERE admin_id = target_user_id OR leader_id = target_user_id;

  -- STEP 7: Delete direct dependencies of target user
  DELETE FROM forum_likes WHERE user_id = target_user_id;
  DELETE FROM forum_posts WHERE created_by = target_user_id;
  DELETE FROM forum_topics WHERE created_by = target_user_id;

  DELETE FROM onboarding_requests 
  WHERE requested_by_id = target_user_id OR reviewed_by_id = target_user_id;

  DELETE FROM sim_cards
  WHERE assigned_to_user_id = target_user_id
     OR sold_by_user_id = target_user_id
     OR registered_by_user_id = target_user_id;

  DELETE FROM payment_requests WHERE user_id = target_user_id;
  DELETE FROM subscriptions WHERE user_id = target_user_id;
  DELETE FROM activity_logs WHERE user_id = target_user_id;

  -- STEP 8: Delete user
  DELETE FROM users WHERE id = target_user_id;

  -- STEP 9: Drop temp table
  DROP TABLE managed_users;

END;
$$;


ALTER PROCEDURE "public"."delete_user_and_dependants"(IN "target_user_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_accessible_user_ids"() RETURNS SETOF "uuid"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
DECLARE
  current_user_role TEXT;
  current_user_team_id UUID;
BEGIN
  -- Get current user's role and team_id
  SELECT role, team_id INTO current_user_role, current_user_team_id
  FROM users
  WHERE auth_user_id = auth.uid();
  
  -- Return user IDs based on role
  RETURN QUERY
  SELECT id FROM users
  WHERE
    -- User can access themselves
    id = get_user_id()
    -- Admin can access users in their teams
    OR (current_user_role = 'admin' AND team_id IN (SELECT * FROM get_administered_team_ids()))
    -- Team leader can access users in their team
    OR (current_user_role = 'team_leader' AND team_id = current_user_team_id);
END;
$$;


ALTER FUNCTION "public"."get_accessible_user_ids"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_administered_team_ids"() RETURNS SETOF "uuid"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
  RETURN QUERY
  SELECT t.id FROM teams t
  JOIN users u ON t.admin_id = u.id
  WHERE u.auth_user_id = auth.uid()
  AND u.role = 'admin';
END;
$$;


ALTER FUNCTION "public"."get_administered_team_ids"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_batches_with_counts"("user_id" "uuid") RETURNS TABLE("id" "uuid", "created_at" timestamp with time zone, "batch_id" "text", "order_number" "text", "requisition_number" "text", "company_name" "text", "collection_point" "text", "move_order_number" "text", "date_created" "text", "lot_numbers" "text"[], "item_description" "text", "quantity" integer, "team_id" "jsonb", "created_by_user_id" "jsonb", "sim_count" bigint)
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
DECLARE
  user_role TEXT;
  user_team_id UUID;
BEGIN
  -- Get user role and team_id
  SELECT role, team_id INTO user_role, user_team_id
  FROM users
  WHERE id = user_id;

  -- Return batches based on user role
  RETURN QUERY
  WITH batch_data AS (
    SELECT 
      bm.id,
      bm.created_at,
      bm.batch_id,
      bm.order_number,
      bm.requisition_number,
      bm.company_name,
      bm.collection_point,
      bm.move_order_number,
      bm.date_created,
      bm.lot_numbers,
      bm.item_description,
      bm.quantity,
      jsonb_build_object(
        'id', t.id,
        'name', t.name,
        'region', t.region
      ) AS team_id,
      jsonb_build_object(
        'id', u.id,
        'full_name', u.full_name
      ) AS created_by_user_id,
      (
        SELECT COUNT(*)
        FROM sim_cards sc
        WHERE sc.batch_id = bm.batch_id
      ) AS sim_count
    FROM 
      batch_metadata bm
      JOIN teams t ON bm.team_id = t.id
      JOIN users u ON bm.created_by_user_id = u.id
    WHERE
      CASE
        WHEN user_role = 'admin' THEN TRUE
        WHEN user_role = 'team_leader' THEN bm.team_id = user_team_id
        ELSE bm.created_by_user_id = user_id
      END
  )
  SELECT * FROM batch_data
  ORDER BY created_at DESC;
END;
$$;


ALTER FUNCTION "public"."get_batches_with_counts"("user_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_comprehensive_security_metrics"() RETURNS TABLE("total_requests" bigint, "blocked_requests" bigint, "suspicious_ips" bigint, "active_threats" bigint, "unique_countries" bigint, "avg_response_time" numeric, "uptime" numeric, "incidents_today" bigint)
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  RETURN QUERY
  SELECT 
    (SELECT COUNT(*) FROM security_request_logs WHERE created_at >= NOW() - INTERVAL '24 hours') as total_requests,
    (SELECT COUNT(*) FROM security_request_logs WHERE blocked = true AND created_at >= NOW() - INTERVAL '24 hours') as blocked_requests,
    (SELECT COUNT(DISTINCT ip_address) FROM security_request_logs WHERE threat_level IN ('medium', 'high', 'critical') AND created_at >= NOW() - INTERVAL '24 hours') as suspicious_ips,
    (SELECT COUNT(DISTINCT ip_address) FROM security_request_logs WHERE threat_level IN ('high', 'critical') AND created_at >= NOW() - INTERVAL '1 hour') as active_threats,
    (SELECT COUNT(DISTINCT country) FROM security_request_logs WHERE created_at >= NOW() - INTERVAL '24 hours' AND country IS NOT NULL) as unique_countries,
    (SELECT COALESCE(AVG(response_time_ms), 0) FROM security_request_logs WHERE created_at >= NOW() - INTERVAL '24 hours' AND response_time_ms IS NOT NULL) as avg_response_time,
    99.97 as uptime, -- Calculate actual uptime based on your monitoring
    (SELECT COUNT(*) FROM security_incidents WHERE DATE(detected_at) = CURRENT_DATE) as incidents_today;
END;
$$;


ALTER FUNCTION "public"."get_comprehensive_security_metrics"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_geographic_threat_distribution"() RETURNS TABLE("country" character varying, "country_name" character varying, "total_requests" bigint, "threat_requests" bigint, "unique_ips" bigint, "avg_risk_score" numeric, "lat" numeric, "lng" numeric)
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  RETURN QUERY
  SELECT 
    rl.country,
    CASE rl.country
      WHEN 'US' THEN 'United States'
      WHEN 'CN' THEN 'China'
      WHEN 'RU' THEN 'Russia'
      WHEN 'DE' THEN 'Germany'
      WHEN 'GB' THEN 'United Kingdom'
      ELSE rl.country
    END as country_name,
    COUNT(*) as total_requests,
    COUNT(*) FILTER (WHERE rl.threat_level IN ('medium', 'high', 'critical')) as threat_requests,
    COUNT(DISTINCT rl.ip_address) as unique_ips,
    COALESCE(AVG(rl.risk_score), 0) as avg_risk_score,
    0.0 as lat, -- Add actual coordinates
    0.0 as lng
  FROM security_request_logs rl
  WHERE rl.created_at >= NOW() - INTERVAL '24 hours'
    AND rl.country IS NOT NULL
  GROUP BY rl.country
  HAVING COUNT(*) FILTER (WHERE rl.threat_level IN ('medium', 'high', 'critical')) > 0
  ORDER BY threat_requests DESC;
END;
$$;


ALTER FUNCTION "public"."get_geographic_threat_distribution"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_my_team_admin_id"() RETURNS "uuid"
    LANGUAGE "sql" STABLE
    AS $$SELECT admin_id 
    FROM users 
    WHERE id = auth.uid()$$;


ALTER FUNCTION "public"."get_my_team_admin_id"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_team_hierarchy"("in_team_id" "uuid") RETURNS TABLE("id" "uuid", "name" "text", "leader_id" "uuid", "leader_name" "text", "member_count" integer, "staff" "json"[])
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  RETURN QUERY
  WITH team_data AS (
    SELECT
      t.id,
      t.name,
      t.leader_id,
      leader.full_name as leader_name,
      (SELECT COUNT(*) FROM users WHERE team_id = t.id AND is_active = true)::INTEGER as active_member_count
    FROM teams t
    LEFT JOIN users leader ON t.leader_id = leader.id
    WHERE t.id = in_team_id
  ),
  team_members AS (
    SELECT
      u.id,
      u.full_name,
      u.role,
      u.staff_type,
      (SELECT COUNT(*) FROM sim_cards WHERE sold_by_user_id = u.id)::INTEGER as sim_sales_count
    FROM users u
    WHERE u.team_id = in_team_id AND u.is_active = true
  )
  SELECT
    td.id,
    td.name,
    td.leader_id,
    td.leader_name,
    td.active_member_count,
    COALESCE(
      array_agg(
        json_build_object(
          'user_id', tm.id,
          'full_name', tm.full_name,
          'role', tm.role,
          'staff_type', tm.staff_type,
          'sim_sales_count', tm.sim_sales_count
        )
      ) FILTER (WHERE tm.id IS NOT NULL),
      '{}'::JSON[]
    ) as staff
  FROM team_data td
  LEFT JOIN team_members tm ON true
  GROUP BY td.id, td.name, td.leader_id, td.leader_name, td.active_member_count;
END;
$$;


ALTER FUNCTION "public"."get_team_hierarchy"("in_team_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_threat_timeline"("hours_back" integer DEFAULT 24) RETURNS TABLE("event_time" timestamp with time zone, "total_requests" bigint, "high_threats" bigint, "critical_threats" bigint, "blocked_requests" bigint, "unique_ips" bigint, "avg_response_time" numeric)
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  RETURN QUERY
  SELECT 
    DATE_TRUNC('hour', rl.created_at) as timestamp,
    COUNT(*) as total_requests,
    COUNT(*) FILTER (WHERE rl.threat_level = 'high') as high_threats,
    COUNT(*) FILTER (WHERE rl.threat_level = 'critical') as critical_threats,
    COUNT(*) FILTER (WHERE rl.blocked = true) as blocked_requests,
    COUNT(DISTINCT rl.ip_address) as unique_ips,
    COALESCE(AVG(rl.response_time_ms), 0) as avg_response_time
  FROM security_request_logs rl
  WHERE rl.created_at >= NOW() - (hours_back || ' hours')::INTERVAL
  GROUP BY DATE_TRUNC('hour', rl.created_at)
  ORDER BY timestamp ASC;
END;
$$;


ALTER FUNCTION "public"."get_threat_timeline"("hours_back" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_top_attacking_ips"("limit_count" integer DEFAULT 20) RETURNS TABLE("ip_address" "inet", "total_requests" bigint, "threat_requests" bigint, "max_risk_score" integer, "countries" "text"[], "last_seen" timestamp with time zone, "is_blocked" boolean, "reputation" integer)
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  RETURN QUERY
  SELECT 
    rl.ip_address,
    COUNT(*) as total_requests,
    COUNT(*) FILTER (WHERE rl.threat_level IN ('medium', 'high', 'critical')) as threat_requests,
    MAX(rl.risk_score) as max_risk_score,
    ARRAY_AGG(DISTINCT rl.country) FILTER (WHERE rl.country IS NOT NULL) as countries,
    MAX(rl.created_at) as last_seen,
    EXISTS(SELECT 1 FROM ip_blocks ib WHERE ib.ip_address = rl.ip_address AND (ib.expires_at IS NULL OR ib.expires_at > NOW())) as is_blocked,
    COALESCE((SELECT ii.reputation_score FROM ip_intelligence ii WHERE ii.ip_address = rl.ip_address), 50) as reputation
  FROM security_request_logs rl
  WHERE rl.created_at >= NOW() - INTERVAL '24 hours'
  GROUP BY rl.ip_address
  HAVING COUNT(*) FILTER (WHERE rl.threat_level IN ('medium', 'high', 'critical')) > 0
  ORDER BY threat_requests DESC, total_requests DESC
  LIMIT limit_count;
END;
$$;


ALTER FUNCTION "public"."get_top_attacking_ips"("limit_count" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_user_id"() RETURNS "uuid"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
DECLARE
  user_id UUID;
BEGIN
  SELECT id INTO user_id FROM users WHERE auth_user_id = auth.uid();
  RETURN user_id;
END;
$$;


ALTER FUNCTION "public"."get_user_id"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_user_role"() RETURNS "text"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
DECLARE
  user_role TEXT;
BEGIN
  SELECT role INTO user_role FROM users WHERE auth_user_id = auth.uid();
  RETURN user_role;
END;
$$;


ALTER FUNCTION "public"."get_user_role"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_user_role_safe"() RETURNS "text"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
DECLARE
  user_role TEXT;
BEGIN
  SELECT role INTO user_role 
  FROM users 
  WHERE auth_user_id = auth.uid()
  LIMIT 1;
  
  RETURN COALESCE(user_role, 'none');
END;
$$;


ALTER FUNCTION "public"."get_user_role_safe"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_user_team_id"() RETURNS "uuid"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
DECLARE
  team_id UUID;
BEGIN
  SELECT users.team_id INTO team_id 
  FROM users 
  WHERE auth_user_id = auth.uid();
  RETURN team_id;
END;
$$;


ALTER FUNCTION "public"."get_user_team_id"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."handle_approved_deletion_request"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
  -- Only proceed if the status was changed to 'APPROVED' and it's a deletion request
  IF NEW.status = 'APPROVED' AND NEW.request_type = 'DELETION' AND 
     (OLD.status != 'APPROVED' OR OLD.status IS NULL) THEN
    
    -- Determine if we should completely delete or just deactivate the user
    -- For this example, we'll deactivate by setting is_active to false and status to SUSPENDED
    -- You could modify this to DELETE FROM users if you want permanent deletion
    
    UPDATE public.users
    SET 
      status = 'SUSPENDED',
      is_active = false
    WHERE id_number = NEW.id_number;
    
    -- Log this activity
    INSERT INTO public.activity_logs (
      id,
      created_at,
      user_id,
      action_type,
      details,
      ip_address,
      is_offline_action
    ) VALUES (
      gen_random_uuid(),
      NOW(),
      NEW.reviewed_by_id,
      'USER_DEACTIVATED',
      jsonb_build_object(
        'request_id', NEW.id,
        'id_number', NEW.id_number,
        'reason', 'Deletion request approved'
      ),
      NULL,
      false
    );
  END IF;
  
  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."handle_approved_deletion_request"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."handle_approved_onboarding_request"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$BEGIN
  -- Only proceed if the status was changed to 'APPROVED'
  IF lower(NEW.status) = 'approved' AND (lower(OLD.status) != 'approved' OR OLD.status IS NULL) THEN
    -- Insert new user based on the approved onboarding request
    INSERT INTO public.users (
      id,
      created_at,
      email,
      full_name,
      id_number,
      id_front_url,
      id_back_url,
      phone_number,
      mobigo_number,
      role,
      team_id,
      status,
      staff_type,
      is_active
    ) VALUES (
      gen_random_uuid(), -- Generate a new UUID
      NOW(), -- Current timestamp
      lower(regexp_replace(NEW.full_name, '[^a-zA-Z0-9]', '', 'g') || '@' || NEW.id_number || '.temp'), -- Generate temporary email from name and ID
      NEW.full_name,
      NEW.id_number,
      NEW.id_front_url,
      NEW.id_back_url,
      NEW.phone_number,
      NEW.mobigo_number,
      NEW.role,
      NEW.team_id,
      'ACTIVE', -- Set initial status to ACTIVE
      NEW.staff_type,
      true -- Set is_active to true
    );
    
    -- Log this activity
    INSERT INTO public.activity_logs (
      id,
      created_at,
      user_id,
      action_type,
      details,
      ip_address,
      is_offline_action
    ) VALUES (
      gen_random_uuid(),
      NOW(),
      NEW.reviewed_by_id,
      'USER_CREATED',
      jsonb_build_object(
        'request_id', NEW.id,
        'full_name', NEW.full_name,
        'role', NEW.role,
        'team_id', NEW.team_id
      ),
      NULL,
      false
    );
  END IF;
  
  RETURN NEW;
END;$$;


ALTER FUNCTION "public"."handle_approved_onboarding_request"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."handle_approved_sim_card_transfer"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
  -- Only proceed if the status was changed to 'approved'
  IF NEW.status = 'approved' AND (OLD.status != 'approved' OR OLD.status IS NULL) THEN
    -- Update the team_id for all SIM cards in the transfer
    UPDATE sim_cards
    SET 
      team_id = NEW.destination_team_id,
      updated_at = NOW()
    WHERE 
      id = ANY(SELECT jsonb_array_elements_text(NEW.sim_cards))
      AND team_id = NEW.source_team_id
      AND status != 'sold'; -- Only transfer unsold SIM cards
    
    -- Update the transfer record with approval information
    NEW.approval_date = NOW();
    NEW.updated_at = NOW();
  END IF;
  
  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."handle_approved_sim_card_transfer"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."has_access_to_user"("target_user_id" "uuid") RETURNS boolean
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
DECLARE
  current_user_role TEXT;
  current_user_team_id UUID;
  target_user_team_id UUID;
BEGIN
  -- Get current user's role and team_id
  SELECT role, team_id INTO current_user_role, current_user_team_id
  FROM users
  WHERE auth_user_id = auth.uid();
  
  -- Get target user's team_id
  SELECT team_id INTO target_user_team_id
  FROM users
  WHERE id = target_user_id;
  
  -- Check access based on role
  RETURN (
    -- User can access themselves
    target_user_id = get_user_id()
    -- Admin can access users in their teams
    OR (current_user_role = 'admin' AND target_user_team_id IN (SELECT * FROM get_administered_team_ids()))
    -- Team leader can access users in their team
    OR (current_user_role = 'team_leader' AND target_user_team_id = current_user_team_id)
  );
END;
$$;


ALTER FUNCTION "public"."has_access_to_user"("target_user_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."is_admin"() RETURNS boolean
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM users
    WHERE auth_user_id = auth.uid()
    AND role = 'admin'
  );
END;
$$;


ALTER FUNCTION "public"."is_admin"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."is_admin_for_team"("team_id" "uuid") RETURNS boolean
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM teams t
    JOIN users u ON t.admin_id = u.id
    WHERE t.id = team_id
    AND u.auth_user_id = auth.uid()
    AND u.role = 'admin'
  );
END;
$$;


ALTER FUNCTION "public"."is_admin_for_team"("team_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."is_leader_of_team"("team_id" "uuid") RETURNS boolean
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM teams
    WHERE id = team_id
    AND leader_id = (SELECT id FROM users WHERE auth_user_id = auth.uid())
  );
END;
$$;


ALTER FUNCTION "public"."is_leader_of_team"("team_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."is_member_of_team"("team_id" "uuid") RETURNS boolean
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM users
    WHERE auth_user_id = auth.uid()
    AND team_id = team_id
  );
END;
$$;


ALTER FUNCTION "public"."is_member_of_team"("team_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."is_team_leader"() RETURNS boolean
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$BEGIN
  RETURN EXISTS (
    SELECT 1 FROM users
    WHERE auth_user_id = auth.uid()
     AND role ILIKE 'team_leader'
  );
END;$$;


ALTER FUNCTION "public"."is_team_leader"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."register_user_session"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
  INSERT INTO user_sessions (
    user_id, 
    device_info, 
    ip_address, 
    user_agent,
    expires_at
  )
  VALUES (
    NEW.user_id,
    COALESCE(NEW.device_info, 'Unknown Device'),
    NEW.ip_address,
    NEW.user_agent,
    NOW() + INTERVAL '30 days'
  );
  
  -- Update active sessions count
  INSERT INTO user_security_activity (user_id, active_sessions, last_login)
  VALUES (NEW.user_id, 1, NOW())
  ON CONFLICT (user_id)
  DO UPDATE SET 
    active_sessions = (
      SELECT COUNT(*) FROM user_sessions 
      WHERE user_id = NEW.user_id
    ),
    last_login = NOW();
  
  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."register_user_session"() OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."sim_cards" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "serial_number" "text" NOT NULL,
    "sold_by_user_id" "uuid",
    "sale_date" timestamp with time zone,
    "sale_location" "text",
    "activation_date" timestamp with time zone,
    "top_up_amount" numeric(10,2),
    "top_up_date" timestamp with time zone,
    "status" "text" DEFAULT 'PENDING'::"text" NOT NULL,
    "team_id" "uuid" NOT NULL,
    "region" "text",
    "fraud_flag" boolean DEFAULT false,
    "fraud_reason" "text",
    "quality" "text" DEFAULT 'NONQUALITY'::"text" NOT NULL,
    "match" "text" DEFAULT 'N'::"text" NOT NULL,
    "assigned_on" timestamp with time zone,
    "updated_at" timestamp with time zone DEFAULT ("now"() AT TIME ZONE 'utc'::"text"),
    "registered_on" timestamp with time zone,
    "assigned_to_user_id" "uuid",
    "registered_by_user_id" "uuid" NOT NULL,
    "batch_id" "text" NOT NULL,
    "admin_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "usage" numeric,
    "in_transit" boolean DEFAULT false,
    "lot" "text",
    "ba_msisdn" "text",
    "mobigo" "text"
);


ALTER TABLE "public"."sim_cards" OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."search_sim_cards"("search_term" "text" DEFAULT NULL::"text", "status_filter" "text" DEFAULT NULL::"text", "team_id_param" "uuid" DEFAULT NULL::"uuid", "from_date" timestamp without time zone DEFAULT NULL::timestamp without time zone, "to_date" timestamp without time zone DEFAULT NULL::timestamp without time zone) RETURNS SETOF "public"."sim_cards"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    RETURN QUERY
    SELECT 
        sc.*
    FROM 
        sim_cards sc
    LEFT JOIN 
        users u ON sc.assigned_to_user_id = u.id
    LEFT JOIN 
        users reg_user ON sc.registered_by_user_id = reg_user.id
    WHERE 
        (search_term IS NULL OR 
         sc.serial_number ILIKE '%' || search_term || '%')
        AND (status_filter IS NULL OR sc.status = status_filter)
        AND (team_id_param IS NULL OR sc.team_id = team_id_param)
        AND (from_date IS NULL OR sc.created_at >= from_date)
        AND (to_date IS NULL OR sc.created_at <= to_date)
    ORDER BY 
        sc.created_at DESC;
END;
$$;


ALTER FUNCTION "public"."search_sim_cards"("search_term" "text", "status_filter" "text", "team_id_param" "uuid", "from_date" timestamp without time zone, "to_date" timestamp without time zone) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."search_sim_cards"("search_term" "text", "status_filter" "text" DEFAULT NULL::"text", "team_id" "uuid" DEFAULT NULL::"uuid", "from_date" timestamp with time zone DEFAULT NULL::timestamp with time zone, "to_date" timestamp with time zone DEFAULT NULL::timestamp with time zone) RETURNS TABLE("id" "uuid", "serial_number" "text", "customer_msisdn" "text", "agent_msisdn" "text", "sold_by_name" "text", "sale_date" timestamp with time zone, "status" "text", "team_name" "text")
    LANGUAGE "plpgsql"
    AS $$BEGIN
  RETURN QUERY
  SELECT
    s.id,
    s.serial_number,
    u.full_name as sold_by_name,
    s.created_at,
    s.status,
    t.name as team_name
  FROM sim_cards s
  JOIN users u ON s.sold_by_user_id = u.id
  JOIN teams t ON s.team_id = t.id
  WHERE (
    search_term IS NULL OR
    s.serial_number ILIKE '%' || search_term || '%' OR
    u.full_name ILIKE '%' || search_term || '%'
  )
  AND (status_filter IS NULL OR s.status = status_filter)
  AND (team_id IS NULL OR s.team_id = team_id)
  AND (from_date IS NULL OR s.created_at >= from_date)
  AND (to_date IS NULL OR s.created_at <= to_date)
  ORDER BY s.created_at DESC;
END;$$;


ALTER FUNCTION "public"."search_sim_cards"("search_term" "text", "status_filter" "text", "team_id" "uuid", "from_date" timestamp with time zone, "to_date" timestamp with time zone) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."set_team_admin_id"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
  -- If admin_id is not set and the current user is an admin, set it
  IF NEW.admin_id IS NULL AND EXISTS (
    SELECT 1 FROM users
    WHERE auth_user_id = auth.uid()
    AND role = 'admin'
  ) THEN
    NEW.admin_id = (SELECT id FROM users WHERE auth_user_id = auth.uid());
  END IF;
  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."set_team_admin_id"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_leader_team_id_on_change"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  -- Only update if leader_id has changed
  IF NEW.leader_id IS DISTINCT FROM OLD.leader_id THEN
    UPDATE users
    SET team_id = NEW.id
    WHERE id = NEW.leader_id;
  END IF;

  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_leader_team_id_on_change"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_registered_on"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  IF NEW.status = 'REGISTERED' AND (OLD.status IS NULL OR OLD.status != 'REGISTERED') THEN
    NEW.registered_on = NOW();
  END IF;
  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_registered_on"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_task_status_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_task_status_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_updated_at_column"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_updated_at_column"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_user_team_id"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  UPDATE users
  SET team_id = NEW.id
  WHERE id = NEW.leader_id;

  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_user_team_id"() OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."activity_logs" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "user_id" "uuid" NOT NULL,
    "action_type" "text" NOT NULL,
    "details" "jsonb" NOT NULL,
    "ip_address" "text",
    "device_info" "text",
    "is_offline_action" boolean DEFAULT false,
    "sync_date" timestamp with time zone
);


ALTER TABLE "public"."activity_logs" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."alert_rules" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "name" character varying(255) NOT NULL,
    "description" "text",
    "condition_sql" "text" NOT NULL,
    "severity" character varying(20) NOT NULL,
    "threshold_value" numeric(10,2),
    "threshold_operator" character varying(10),
    "evaluation_window_minutes" integer DEFAULT 5,
    "notification_channels" "text"[],
    "auto_block" boolean DEFAULT false,
    "create_incident" boolean DEFAULT false,
    "enabled" boolean DEFAULT true,
    "last_triggered" timestamp with time zone,
    "trigger_count" integer DEFAULT 0,
    "created_by" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "valid_operator" CHECK ((("threshold_operator")::"text" = ANY ((ARRAY['>'::character varying, '<'::character varying, '>='::character varying, '<='::character varying, '='::character varying, '!='::character varying])::"text"[]))),
    CONSTRAINT "valid_severity" CHECK ((("severity")::"text" = ANY ((ARRAY['low'::character varying, 'medium'::character varying, 'high'::character varying, 'critical'::character varying])::"text"[])))
);


ALTER TABLE "public"."alert_rules" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."batch_metadata" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "batch_id" "text" NOT NULL,
    "order_number" "text",
    "requisition_number" "text",
    "company_name" "text",
    "collection_point" "text",
    "move_order_number" "text",
    "date_created" "text",
    "lot_numbers" "text"[],
    "item_description" "text",
    "quantity" integer,
    "team_id" "uuid" NOT NULL,
    "created_by_user_id" "uuid" NOT NULL,
    "teams" "text"[] DEFAULT '{}'::"text"[]
);


ALTER TABLE "public"."batch_metadata" OWNER TO "postgres";


COMMENT ON COLUMN "public"."batch_metadata"."teams" IS 'Array of team IDs associated with this batch';



CREATE TABLE IF NOT EXISTS "public"."config" (
    "key" "text" NOT NULL,
    "value" "jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."config" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."detection_rules" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "name" character varying(255) NOT NULL,
    "description" "text",
    "rule_type" character varying(50) NOT NULL,
    "pattern" "text" NOT NULL,
    "threat_level" character varying(20) NOT NULL,
    "categories" "text"[],
    "confidence" numeric(3,2) DEFAULT 1.0,
    "action" character varying(50) DEFAULT 'log'::character varying,
    "auto_block_duration_minutes" integer,
    "enabled" boolean DEFAULT true,
    "false_positive_rate" numeric(5,4) DEFAULT 0.0,
    "last_match" timestamp with time zone,
    "match_count" bigint DEFAULT 0,
    "created_by" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "valid_action" CHECK ((("action")::"text" = ANY ((ARRAY['log'::character varying, 'alert'::character varying, 'block'::character varying, 'challenge'::character varying])::"text"[]))),
    CONSTRAINT "valid_rule_type" CHECK ((("rule_type")::"text" = ANY ((ARRAY['signature'::character varying, 'behavioral'::character varying, 'anomaly'::character varying, 'reputation'::character varying])::"text"[])))
);


ALTER TABLE "public"."detection_rules" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."forum_likes" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "topic_id" "uuid",
    "post_id" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "topic_or_post_required" CHECK (((("topic_id" IS NOT NULL) AND ("post_id" IS NULL)) OR (("topic_id" IS NULL) AND ("post_id" IS NOT NULL))))
);


ALTER TABLE "public"."forum_likes" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."forum_posts" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "topic_id" "uuid" NOT NULL,
    "content" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "created_by" "uuid" NOT NULL
);


ALTER TABLE "public"."forum_posts" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."forum_topics" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "title" "text" NOT NULL,
    "content" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "created_by" "uuid" NOT NULL,
    "is_pinned" boolean DEFAULT false,
    "is_closed" boolean DEFAULT false,
    "view_count" integer DEFAULT 0
);


ALTER TABLE "public"."forum_topics" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."public_user_profiles" WITH ("security_invoker"='on') AS
 SELECT "users"."id",
    "users"."full_name",
    "users"."email"
   FROM "public"."users";


ALTER TABLE "public"."public_user_profiles" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."forum_topics_with_author" AS
 SELECT "t"."id",
    "t"."title",
    "t"."content",
    "t"."created_at",
    "t"."updated_at",
    "t"."created_by",
    "t"."is_pinned",
    "t"."is_closed",
    "t"."view_count",
    "u"."full_name",
    "u"."email"
   FROM ("public"."forum_topics" "t"
     LEFT JOIN "public"."public_user_profiles" "u" ON (("t"."created_by" = "u"."id")));


ALTER TABLE "public"."forum_topics_with_author" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."security_request_logs" (
    "id" bigint NOT NULL,
    "request_id" "uuid" DEFAULT "extensions"."uuid_generate_v4"(),
    "ip_address" "inet" NOT NULL,
    "user_agent" "text",
    "referer" "text",
    "origin" "text",
    "method" character varying(10) NOT NULL,
    "path" "text" NOT NULL,
    "query_params" "jsonb",
    "headers" "jsonb",
    "body_size" integer,
    "country" character varying(2),
    "region" character varying(100),
    "city" character varying(100),
    "asn" integer,
    "isp" character varying(255),
    "threat_level" character varying(20) DEFAULT 'safe'::character varying,
    "threat_categories" "text"[],
    "risk_score" integer DEFAULT 0,
    "confidence_score" numeric(3,2) DEFAULT 0.0,
    "signature_matches" "text"[],
    "behavioral_flags" "text"[],
    "anomaly_score" numeric(5,4) DEFAULT 0.0,
    "response_status" integer,
    "response_time_ms" integer,
    "blocked" boolean DEFAULT false,
    "challenge_issued" boolean DEFAULT false,
    "session_id" character varying(255),
    "user_id" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "processed_at" timestamp with time zone,
    CONSTRAINT "valid_risk_score" CHECK ((("risk_score" >= 0) AND ("risk_score" <= 100))),
    CONSTRAINT "valid_threat_level" CHECK ((("threat_level")::"text" = ANY ((ARRAY['safe'::character varying, 'low'::character varying, 'medium'::character varying, 'high'::character varying, 'critical'::character varying])::"text"[])))
);


ALTER TABLE "public"."security_request_logs" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."geographic_threat_distribution" AS
 SELECT "security_request_logs"."country",
    "count"(*) AS "total_requests",
    "count"(*) FILTER (WHERE (("security_request_logs"."threat_level")::"text" = ANY ((ARRAY['high'::character varying, 'critical'::character varying])::"text"[]))) AS "threat_requests",
    "count"(DISTINCT "security_request_logs"."ip_address") AS "unique_ips",
    "round"("avg"("security_request_logs"."risk_score"), 2) AS "avg_risk_score"
   FROM "public"."security_request_logs"
  WHERE (("security_request_logs"."created_at" >= ("now"() - '24:00:00'::interval)) AND ("security_request_logs"."country" IS NOT NULL))
  GROUP BY "security_request_logs"."country"
  ORDER BY ("count"(*) FILTER (WHERE (("security_request_logs"."threat_level")::"text" = ANY ((ARRAY['high'::character varying, 'critical'::character varying])::"text"[])))) DESC;


ALTER TABLE "public"."geographic_threat_distribution" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."incident_events" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "incident_id" "uuid" NOT NULL,
    "event_type" character varying(50) NOT NULL,
    "description" "text" NOT NULL,
    "actor" character varying(255),
    "occurred_at" timestamp with time zone DEFAULT "now"(),
    "created_at" timestamp with time zone DEFAULT "now"(),
    "metadata" "jsonb",
    "automated" boolean DEFAULT false
);


ALTER TABLE "public"."incident_events" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."ip_blocks" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "ip_address" "inet" NOT NULL,
    "block_type" character varying(20) DEFAULT 'temporary'::character varying NOT NULL,
    "reason" "text" NOT NULL,
    "severity" character varying(20) DEFAULT 'medium'::character varying,
    "blocked_at" timestamp with time zone DEFAULT "now"(),
    "expires_at" timestamp with time zone,
    "created_by" "uuid",
    "incident_id" "uuid",
    "rule_id" "uuid",
    "auto_generated" boolean DEFAULT false,
    "requests_blocked" bigint DEFAULT 0,
    "last_attempted" timestamp with time zone,
    CONSTRAINT "valid_block_type" CHECK ((("block_type")::"text" = ANY ((ARRAY['temporary'::character varying, 'permanent'::character varying, 'whitelist'::character varying])::"text"[]))),
    CONSTRAINT "valid_severity" CHECK ((("severity")::"text" = ANY ((ARRAY['low'::character varying, 'medium'::character varying, 'high'::character varying, 'critical'::character varying])::"text"[])))
);


ALTER TABLE "public"."ip_blocks" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."ip_intelligence" (
    "ip_address" "inet" NOT NULL,
    "reputation_score" integer DEFAULT 50,
    "threat_types" "text"[],
    "last_seen_malicious" timestamp with time zone,
    "confidence_level" character varying(20) DEFAULT 'unknown'::character varying,
    "country" character varying(2),
    "region" character varying(100),
    "city" character varying(100),
    "latitude" numeric(9,6),
    "longitude" numeric(9,6),
    "asn" integer,
    "isp" character varying(255),
    "is_tor" boolean DEFAULT false,
    "is_vpn" boolean DEFAULT false,
    "is_proxy" boolean DEFAULT false,
    "is_hosting" boolean DEFAULT false,
    "is_residential" boolean DEFAULT true,
    "total_requests" bigint DEFAULT 0,
    "malicious_requests" bigint DEFAULT 0,
    "countries_seen" "text"[],
    "user_agents_seen" "text"[],
    "first_seen" timestamp with time zone DEFAULT "now"(),
    "last_updated" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "valid_confidence" CHECK ((("confidence_level")::"text" = ANY ((ARRAY['unknown'::character varying, 'low'::character varying, 'medium'::character varying, 'high'::character varying, 'verified'::character varying])::"text"[]))),
    CONSTRAINT "valid_reputation" CHECK ((("reputation_score" >= 0) AND ("reputation_score" <= 100)))
);


ALTER TABLE "public"."ip_intelligence" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."notifications" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "title" "text" NOT NULL,
    "message" "text" NOT NULL,
    "type" "text" NOT NULL,
    "read" boolean DEFAULT false NOT NULL,
    "metadata" "jsonb" DEFAULT '{}'::"jsonb",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "notifications_type_check" CHECK (("type" = ANY (ARRAY['auth'::"text", 'system'::"text", 'user'::"text"])))
);


ALTER TABLE "public"."notifications" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."onboarding_requests" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "requested_by_id" "uuid" NOT NULL,
    "full_name" "text" NOT NULL,
    "id_number" "text" NOT NULL,
    "id_front_url" "text" NOT NULL,
    "id_back_url" "text" NOT NULL,
    "phone_number" "text",
    "mobigo_number" "text",
    "role" "text" NOT NULL,
    "team_id" "uuid",
    "staff_type" "text",
    "status" "text" DEFAULT 'pending'::"text" NOT NULL,
    "reviewed_by_id" "uuid",
    "review_date" timestamp with time zone,
    "review_notes" "text",
    "request_type" "text" DEFAULT ''::"text" NOT NULL,
    "email" "text",
    "admin_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "username" "text",
    "user_id" "uuid"
);


ALTER TABLE "public"."onboarding_requests" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."password_reset_requests" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "token" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "expires_at" timestamp with time zone NOT NULL,
    "used" boolean DEFAULT false
);


ALTER TABLE "public"."password_reset_requests" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."payment_requests" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "reference" "text" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "amount" numeric(10,2) NOT NULL,
    "plan_id" "text" NOT NULL,
    "phone_number" "text" NOT NULL,
    "status" "text" DEFAULT 'pending'::"text" NOT NULL,
    "provider_id" "text",
    "checkout_url" "text",
    "transaction_id" "text",
    "payment_method" "text",
    "payment_details" "jsonb"
);


ALTER TABLE "public"."payment_requests" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."real_time_threat_overview" AS
 SELECT "date_trunc"('minute'::"text", "security_request_logs"."created_at") AS "minute_bucket",
    "count"(*) AS "total_requests",
    "count"(DISTINCT "security_request_logs"."ip_address") AS "unique_ips",
    "count"(*) FILTER (WHERE (("security_request_logs"."threat_level")::"text" = 'high'::"text")) AS "high_threats",
    "count"(*) FILTER (WHERE (("security_request_logs"."threat_level")::"text" = 'critical'::"text")) AS "critical_threats",
    "count"(*) FILTER (WHERE ("security_request_logs"."blocked" = true)) AS "blocked_requests",
    "avg"("security_request_logs"."response_time_ms") AS "avg_response_time"
   FROM "public"."security_request_logs"
  WHERE ("security_request_logs"."created_at" >= ("now"() - '01:00:00'::interval))
  GROUP BY ("date_trunc"('minute'::"text", "security_request_logs"."created_at"))
  ORDER BY ("date_trunc"('minute'::"text", "security_request_logs"."created_at")) DESC;


ALTER TABLE "public"."real_time_threat_overview" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."security_alerts" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "rule_id" "uuid",
    "title" character varying(255) NOT NULL,
    "message" "text" NOT NULL,
    "severity" character varying(20) NOT NULL,
    "trigger_value" numeric(10,2),
    "trigger_data" "jsonb",
    "status" character varying(20) DEFAULT 'active'::character varying,
    "acknowledged_by" "uuid",
    "acknowledged_at" timestamp with time zone,
    "resolved_at" timestamp with time zone,
    "notification_sent" boolean DEFAULT false,
    "notification_channels" "text"[],
    "related_incident_id" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "valid_status" CHECK ((("status")::"text" = ANY ((ARRAY['active'::character varying, 'acknowledged'::character varying, 'resolved'::character varying, 'suppressed'::character varying])::"text"[])))
);


ALTER TABLE "public"."security_alerts" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."security_config" (
    "key" character varying(255) NOT NULL,
    "value" "jsonb" NOT NULL,
    "description" "text",
    "category" character varying(100),
    "updated_by" "uuid",
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."security_config" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."security_incidents" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "title" character varying(255) NOT NULL,
    "description" "text",
    "severity" character varying(20) NOT NULL,
    "status" character varying(20) DEFAULT 'open'::character varying,
    "category" character varying(50),
    "attack_vector" character varying(100),
    "affected_systems" "text"[],
    "impact_assessment" "text",
    "detected_at" timestamp with time zone NOT NULL,
    "started_at" timestamp with time zone,
    "resolved_at" timestamp with time zone,
    "assigned_to" "uuid",
    "escalated_to" "uuid",
    "team" character varying(100),
    "mttr_minutes" integer,
    "false_positive" boolean DEFAULT false,
    "related_incidents" "uuid"[],
    "source_ips" "inet"[],
    "affected_endpoints" "text"[],
    "containment_actions" "text"[],
    "mitigation_steps" "text"[],
    "lessons_learned" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "valid_severity" CHECK ((("severity")::"text" = ANY ((ARRAY['low'::character varying, 'medium'::character varying, 'high'::character varying, 'critical'::character varying])::"text"[]))),
    CONSTRAINT "valid_status" CHECK ((("status")::"text" = ANY ((ARRAY['open'::character varying, 'investigating'::character varying, 'contained'::character varying, 'resolved'::character varying, 'closed'::character varying])::"text"[])))
);


ALTER TABLE "public"."security_incidents" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."security_metrics_daily" (
    "id" bigint NOT NULL,
    "date_bucket" "date" NOT NULL,
    "total_requests" bigint DEFAULT 0,
    "unique_ips" integer DEFAULT 0,
    "unique_countries" integer DEFAULT 0,
    "blocked_requests" bigint DEFAULT 0,
    "incidents_created" integer DEFAULT 0,
    "threat_distribution" "jsonb",
    "geographic_distribution" "jsonb",
    "attack_pattern_analysis" "jsonb",
    "avg_response_time" numeric(8,2),
    "uptime_percentage" numeric(5,2),
    "peak_traffic_hour" integer,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."security_metrics_daily" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."security_metrics_daily_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "public"."security_metrics_daily_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."security_metrics_daily_id_seq" OWNED BY "public"."security_metrics_daily"."id";



CREATE TABLE IF NOT EXISTS "public"."security_metrics_hourly" (
    "id" bigint NOT NULL,
    "hour_bucket" timestamp with time zone NOT NULL,
    "total_requests" bigint DEFAULT 0,
    "unique_ips" integer DEFAULT 0,
    "blocked_requests" bigint DEFAULT 0,
    "safe_requests" bigint DEFAULT 0,
    "low_threat_requests" bigint DEFAULT 0,
    "medium_threat_requests" bigint DEFAULT 0,
    "high_threat_requests" bigint DEFAULT 0,
    "critical_threat_requests" bigint DEFAULT 0,
    "top_countries" "jsonb",
    "avg_response_time" numeric(8,2),
    "p95_response_time" numeric(8,2),
    "error_rate" numeric(5,2),
    "top_attack_vectors" "jsonb",
    "top_threat_ips" "jsonb",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."security_metrics_hourly" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."security_metrics_hourly_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "public"."security_metrics_hourly_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."security_metrics_hourly_id_seq" OWNED BY "public"."security_metrics_hourly"."id";



CREATE SEQUENCE IF NOT EXISTS "public"."security_request_logs_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "public"."security_request_logs_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."security_request_logs_id_seq" OWNED BY "public"."security_request_logs"."id";



CREATE TABLE IF NOT EXISTS "public"."sim_card_transfers" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "source_team_id" "uuid" NOT NULL,
    "destination_team_id" "uuid" NOT NULL,
    "requested_by_id" "uuid" NOT NULL,
    "approved_by_id" "uuid",
    "approval_date" timestamp with time zone,
    "status" "text" DEFAULT 'PENDING'::"text" NOT NULL,
    "reason" "text",
    "notes" "text",
    "sim_cards" "jsonb" NOT NULL,
    "admin_id" "uuid" NOT NULL
);


ALTER TABLE "public"."sim_card_transfers" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."teams" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "name" "text" NOT NULL,
    "leader_id" "uuid",
    "region" "text" NOT NULL,
    "territory" "text",
    "van_number_plate" "text",
    "van_location" "text",
    "is_active" boolean DEFAULT true,
    "admin_id" "uuid"
);


ALTER TABLE "public"."teams" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."staff_performance" AS
 SELECT "u"."id" AS "user_id",
    "u"."full_name",
    "t"."id" AS "team_id",
    "t"."name" AS "team_name",
    "count"("s"."id") AS "sim_cards_sold",
    COALESCE((("sum"(
        CASE
            WHEN ("s"."status" = 'activated'::"text") THEN 1
            ELSE 0
        END))::double precision / (NULLIF("count"("s"."id"), 0))::double precision), (0)::double precision) AS "activation_rate",
    COALESCE("avg"("s"."top_up_amount"), (0)::numeric) AS "avg_top_up",
    "count"(
        CASE
            WHEN ("s"."fraud_flag" = true) THEN 1
            ELSE NULL::integer
        END) AS "fraud_flags",
    "to_char"("date_trunc"('month'::"text", "s"."sale_date"), 'YYYY-MM'::"text") AS "period"
   FROM (("public"."users" "u"
     JOIN "public"."teams" "t" ON (("u"."team_id" = "t"."id")))
     LEFT JOIN "public"."sim_cards" "s" ON (("u"."id" = "s"."sold_by_user_id")))
  WHERE ("u"."role" = 'staff'::"text")
  GROUP BY "u"."id", "u"."full_name", "t"."id", "t"."name", ("to_char"("date_trunc"('month'::"text", "s"."sale_date"), 'YYYY-MM'::"text"));


ALTER TABLE "public"."staff_performance" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."subscription_plans" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "name" character varying(255) NOT NULL,
    "description" "text",
    "price_monthly" integer NOT NULL,
    "price_annual" integer NOT NULL,
    "features" "jsonb" DEFAULT '[]'::"jsonb" NOT NULL,
    "is_recommended" boolean DEFAULT false,
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."subscription_plans" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."subscriptions" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "user_id" "uuid" NOT NULL,
    "plan_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "status" "text" DEFAULT 'active'::"text" NOT NULL,
    "starts_at" timestamp with time zone NOT NULL,
    "expires_at" timestamp with time zone NOT NULL,
    "payment_reference" "text",
    "auto_renew" boolean DEFAULT false,
    "cancellation_date" timestamp with time zone,
    "cancellation_reason" "text"
);


ALTER TABLE "public"."subscriptions" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."subscription_status" AS
 SELECT "u"."id" AS "user_id",
    "u"."full_name",
    "u"."email",
    "s"."plan_id",
    "s"."status",
    "s"."starts_at",
    "s"."expires_at",
        CASE
            WHEN (("s"."status" = 'active'::"text") AND ("s"."expires_at" > "now"())) THEN true
            ELSE false
        END AS "is_active",
    EXTRACT(day FROM ("s"."expires_at" - "now"())) AS "days_remaining",
    "p"."amount" AS "last_payment_amount",
    "p"."created_at" AS "last_payment_date"
   FROM (("public"."users" "u"
     LEFT JOIN "public"."subscriptions" "s" ON ((("u"."id" = "s"."user_id") AND ("s"."status" = 'active'::"text"))))
     LEFT JOIN "public"."payment_requests" "p" ON (("s"."payment_reference" = "p"."reference")))
  WHERE ("s"."id" IS NOT NULL);


ALTER TABLE "public"."subscription_status" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."task_status" (
    "id" character varying(255) NOT NULL,
    "user_id" "uuid" NOT NULL,
    "status" character varying(20) NOT NULL,
    "progress" integer DEFAULT 0,
    "total_records" integer DEFAULT 0,
    "processed_records" integer DEFAULT 0,
    "start_time" timestamp with time zone DEFAULT "now"(),
    "end_time" timestamp with time zone,
    "error_message" "text",
    "metadata" "jsonb" DEFAULT '{}'::"jsonb",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "task_status_progress_check" CHECK ((("progress" >= 0) AND ("progress" <= 100))),
    CONSTRAINT "task_status_status_check" CHECK ((("status")::"text" = ANY ((ARRAY['pending'::character varying, 'running'::character varying, 'completed'::character varying, 'failed'::character varying])::"text"[])))
);


ALTER TABLE "public"."task_status" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."team_performance" AS
 SELECT "t"."id" AS "team_id",
    "t"."name" AS "team_name",
    "t"."region" AS "team_region",
    "t"."territory" AS "team_territory",
    "u"."id" AS "leader_id",
    "u"."full_name" AS "leader_name",
    "count"("s"."id") AS "sim_cards_sold",
    "sum"(
        CASE
            WHEN ("s"."quality" = 'QUALITY'::"text") THEN 1
            ELSE 0
        END) AS "quality_count",
    "sum"(
        CASE
            WHEN (("s"."quality" <> 'QUALITY'::"text") OR ("s"."quality" IS NULL)) THEN 1
            ELSE 0
        END) AS "non_quality_count",
    COALESCE((("sum"(
        CASE
            WHEN ("s"."quality" = 'QUALITY'::"text") THEN 1
            ELSE 0
        END))::double precision / (NULLIF("count"("s"."id"), 0))::double precision), (0)::double precision) AS "quality_rate",
    "sum"(
        CASE
            WHEN ("s"."match" = 'Y'::"text") THEN 1
            ELSE 0
        END) AS "matched_count",
    "sum"(
        CASE
            WHEN (("s"."match" <> 'Y'::"text") OR ("s"."match" IS NULL)) THEN 1
            ELSE 0
        END) AS "unmatched_count",
    COALESCE((("sum"(
        CASE
            WHEN ("s"."match" = 'Y'::"text") THEN 1
            ELSE 0
        END))::double precision / (NULLIF("count"("s"."id"), 0))::double precision), (0)::double precision) AS "match_rate",
    COALESCE("avg"("s"."top_up_amount"), (0)::numeric) AS "avg_top_up",
    "count"(
        CASE
            WHEN ("s"."fraud_flag" = true) THEN 1
            ELSE NULL::integer
        END) AS "fraud_flags",
    "array_agg"(
        CASE
            WHEN ("s"."id" IS NOT NULL) THEN "json_build_object"('id', "s"."id", 'user_id', "s"."sold_by_user_id", 'user_name', "su"."full_name", 'quality', "s"."quality", 'match', "s"."match", 'sale_date', "s"."sale_date", 'top_up_amount', "s"."top_up_amount", 'staff_type', "su"."staff_type")
            ELSE NULL::"json"
        END) FILTER (WHERE ("s"."id" IS NOT NULL)) AS "individual_records",
    "to_char"("date_trunc"('month'::"text", "s"."sale_date"), 'YYYY-MM'::"text") AS "period"
   FROM ((("public"."teams" "t"
     LEFT JOIN "public"."users" "u" ON (("t"."leader_id" = "u"."id")))
     LEFT JOIN "public"."sim_cards" "s" ON (("t"."id" = "s"."team_id")))
     LEFT JOIN "public"."users" "su" ON (("s"."sold_by_user_id" = "su"."id")))
  WHERE ("t"."is_active" = true)
  GROUP BY "t"."id", "t"."name", "t"."region", "t"."territory", "u"."id", "u"."full_name", ("to_char"("date_trunc"('month'::"text", "s"."sale_date"), 'YYYY-MM'::"text"));


ALTER TABLE "public"."team_performance" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."top_attacking_ips" AS
 SELECT "security_request_logs"."ip_address",
    "count"(*) AS "total_requests",
    "count"(*) FILTER (WHERE (("security_request_logs"."threat_level")::"text" = ANY ((ARRAY['high'::character varying, 'critical'::character varying])::"text"[]))) AS "threat_requests",
    "max"("security_request_logs"."risk_score") AS "max_risk_score",
    "array_agg"(DISTINCT "security_request_logs"."country") AS "countries",
    "max"("security_request_logs"."created_at") AS "last_seen",
    "bool_or"("security_request_logs"."blocked") AS "is_blocked"
   FROM "public"."security_request_logs"
  WHERE ("security_request_logs"."created_at" >= ("now"() - '24:00:00'::interval))
  GROUP BY "security_request_logs"."ip_address"
 HAVING ("count"(*) FILTER (WHERE (("security_request_logs"."threat_level")::"text" = ANY ((ARRAY['high'::character varying, 'critical'::character varying])::"text"[]))) > 0)
  ORDER BY ("count"(*) FILTER (WHERE (("security_request_logs"."threat_level")::"text" = ANY ((ARRAY['high'::character varying, 'critical'::character varying])::"text"[])))) DESC, ("count"(*)) DESC;


ALTER TABLE "public"."top_attacking_ips" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."two_factor_verifications" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "method" "text" NOT NULL,
    "identifier" "text",
    "code" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "expires_at" timestamp with time zone NOT NULL,
    "verified" boolean DEFAULT false
);


ALTER TABLE "public"."two_factor_verifications" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."user_security_activity" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "last_password_change" timestamp with time zone,
    "last_login" timestamp with time zone,
    "active_sessions" integer DEFAULT 0,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."user_security_activity" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."user_security_settings" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "two_factor_enabled" boolean DEFAULT false,
    "two_factor_method" "text" DEFAULT 'email'::"text",
    "two_factor_verified" boolean DEFAULT false,
    "phone_number" "text",
    "recovery_email" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."user_security_settings" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."user_sessions" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "device_info" "text" NOT NULL,
    "ip_address" "text",
    "user_agent" "text",
    "last_active" timestamp with time zone DEFAULT "now"(),
    "created_at" timestamp with time zone DEFAULT "now"(),
    "expires_at" timestamp with time zone
);


ALTER TABLE "public"."user_sessions" OWNER TO "postgres";


ALTER TABLE ONLY "public"."security_metrics_daily" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."security_metrics_daily_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."security_metrics_hourly" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."security_metrics_hourly_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."security_request_logs" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."security_request_logs_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."activity_logs"
    ADD CONSTRAINT "activity_logs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."alert_rules"
    ADD CONSTRAINT "alert_rules_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."batch_metadata"
    ADD CONSTRAINT "batch_metadata_batch_id_key" UNIQUE ("batch_id");



ALTER TABLE ONLY "public"."batch_metadata"
    ADD CONSTRAINT "batch_metadata_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."config"
    ADD CONSTRAINT "config_pkey" PRIMARY KEY ("key");



ALTER TABLE ONLY "public"."detection_rules"
    ADD CONSTRAINT "detection_rules_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."forum_likes"
    ADD CONSTRAINT "forum_likes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."forum_posts"
    ADD CONSTRAINT "forum_posts_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."forum_topics"
    ADD CONSTRAINT "forum_topics_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."incident_events"
    ADD CONSTRAINT "incident_events_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."ip_blocks"
    ADD CONSTRAINT "ip_blocks_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."ip_intelligence"
    ADD CONSTRAINT "ip_intelligence_pkey" PRIMARY KEY ("ip_address");



ALTER TABLE ONLY "public"."notifications"
    ADD CONSTRAINT "notifications_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."onboarding_requests"
    ADD CONSTRAINT "onboarding_requests_email_key" UNIQUE ("email");



ALTER TABLE ONLY "public"."onboarding_requests"
    ADD CONSTRAINT "onboarding_requests_phone_number_key" UNIQUE ("phone_number");



ALTER TABLE ONLY "public"."onboarding_requests"
    ADD CONSTRAINT "onboarding_requests_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."onboarding_requests"
    ADD CONSTRAINT "onboarding_requests_username_key" UNIQUE ("username");



ALTER TABLE ONLY "public"."password_reset_requests"
    ADD CONSTRAINT "password_reset_requests_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."payment_requests"
    ADD CONSTRAINT "payment_requests_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."payment_requests"
    ADD CONSTRAINT "payment_requests_reference_key" UNIQUE ("reference");



ALTER TABLE ONLY "public"."security_alerts"
    ADD CONSTRAINT "security_alerts_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."security_config"
    ADD CONSTRAINT "security_config_pkey" PRIMARY KEY ("key");



ALTER TABLE ONLY "public"."security_incidents"
    ADD CONSTRAINT "security_incidents_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."security_metrics_daily"
    ADD CONSTRAINT "security_metrics_daily_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."security_metrics_hourly"
    ADD CONSTRAINT "security_metrics_hourly_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."security_request_logs"
    ADD CONSTRAINT "security_request_logs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."sim_card_transfers"
    ADD CONSTRAINT "sim_card_transfers_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."sim_cards"
    ADD CONSTRAINT "sim_cards_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."sim_cards"
    ADD CONSTRAINT "sim_cards_serial_number_key" UNIQUE ("serial_number");



ALTER TABLE ONLY "public"."subscription_plans"
    ADD CONSTRAINT "subscription_plans_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."subscriptions"
    ADD CONSTRAINT "subscriptions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."task_status"
    ADD CONSTRAINT "task_status_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."teams"
    ADD CONSTRAINT "teams_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."two_factor_verifications"
    ADD CONSTRAINT "two_factor_verifications_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."forum_likes"
    ADD CONSTRAINT "unique_post_like" UNIQUE ("user_id", "post_id");



ALTER TABLE ONLY "public"."forum_likes"
    ADD CONSTRAINT "unique_topic_like" UNIQUE ("user_id", "topic_id");



ALTER TABLE ONLY "public"."user_security_activity"
    ADD CONSTRAINT "user_security_activity_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."user_security_activity"
    ADD CONSTRAINT "user_security_activity_user_id_key" UNIQUE ("user_id");



ALTER TABLE ONLY "public"."user_security_settings"
    ADD CONSTRAINT "user_security_settings_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."user_security_settings"
    ADD CONSTRAINT "user_security_settings_user_id_key" UNIQUE ("user_id");



ALTER TABLE ONLY "public"."user_sessions"
    ADD CONSTRAINT "user_sessions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."users"
    ADD CONSTRAINT "users_auth_user_id_key" UNIQUE ("auth_user_id");



ALTER TABLE ONLY "public"."users"
    ADD CONSTRAINT "users_email_key" UNIQUE ("email");



ALTER TABLE ONLY "public"."users"
    ADD CONSTRAINT "users_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."users"
    ADD CONSTRAINT "users_username_key" UNIQUE ("username");



CREATE INDEX "idx_batch_metadata_batch_id" ON "public"."batch_metadata" USING "btree" ("batch_id");



CREATE INDEX "idx_batch_metadata_created_at" ON "public"."batch_metadata" USING "btree" ("created_at");



CREATE INDEX "idx_batch_metadata_created_by" ON "public"."batch_metadata" USING "btree" ("created_by_user_id");



CREATE INDEX "idx_batch_metadata_team_id" ON "public"."batch_metadata" USING "btree" ("team_id");



CREATE INDEX "idx_forum_likes_post_id" ON "public"."forum_likes" USING "btree" ("post_id");



CREATE INDEX "idx_forum_likes_topic_id" ON "public"."forum_likes" USING "btree" ("topic_id");



CREATE INDEX "idx_forum_likes_user_id" ON "public"."forum_likes" USING "btree" ("user_id");



CREATE INDEX "idx_forum_posts_created_by" ON "public"."forum_posts" USING "btree" ("created_by");



CREATE INDEX "idx_forum_posts_topic_id" ON "public"."forum_posts" USING "btree" ("topic_id");



CREATE INDEX "idx_forum_topics_created_at" ON "public"."forum_topics" USING "btree" ("created_at");



CREATE INDEX "idx_forum_topics_created_by" ON "public"."forum_topics" USING "btree" ("created_by");



CREATE INDEX "idx_incident_events_incident" ON "public"."incident_events" USING "btree" ("incident_id", "occurred_at");



CREATE INDEX "idx_ip_blocks_expires" ON "public"."ip_blocks" USING "btree" ("expires_at");



CREATE INDEX "idx_ip_blocks_ip" ON "public"."ip_blocks" USING "btree" ("ip_address");



CREATE INDEX "idx_logs_action" ON "public"."activity_logs" USING "btree" ("action_type");



CREATE INDEX "idx_logs_created" ON "public"."activity_logs" USING "btree" ("created_at");



CREATE INDEX "idx_logs_user" ON "public"."activity_logs" USING "btree" ("user_id");



CREATE UNIQUE INDEX "idx_metrics_daily_bucket" ON "public"."security_metrics_daily" USING "btree" ("date_bucket");



CREATE UNIQUE INDEX "idx_metrics_hourly_bucket" ON "public"."security_metrics_hourly" USING "btree" ("hour_bucket");



CREATE INDEX "idx_payment_reference" ON "public"."payment_requests" USING "btree" ("reference");



CREATE INDEX "idx_payment_status" ON "public"."payment_requests" USING "btree" ("status");



CREATE INDEX "idx_payment_user" ON "public"."payment_requests" USING "btree" ("user_id");



CREATE INDEX "idx_request_logs_country_time" ON "public"."security_request_logs" USING "btree" ("country", "created_at" DESC);



CREATE INDEX "idx_request_logs_ip_time" ON "public"."security_request_logs" USING "btree" ("ip_address", "created_at" DESC);



CREATE INDEX "idx_request_logs_path_time" ON "public"."security_request_logs" USING "btree" ("path", "created_at" DESC);



CREATE INDEX "idx_request_logs_risk_time" ON "public"."security_request_logs" USING "btree" ("risk_score", "created_at" DESC);



CREATE INDEX "idx_request_logs_threat_time" ON "public"."security_request_logs" USING "btree" ("threat_level", "created_at" DESC);



CREATE INDEX "idx_request_status" ON "public"."onboarding_requests" USING "btree" ("status");



CREATE INDEX "idx_sim_cards_in_transit" ON "public"."sim_cards" USING "btree" ("in_transit");



CREATE INDEX "idx_sim_cards_lot" ON "public"."sim_cards" USING "btree" ("lot");



CREATE INDEX "idx_sim_cards_registered_on" ON "public"."sim_cards" USING "btree" ("registered_on");



CREATE INDEX "idx_sim_cards_sold_by_user_id" ON "public"."sim_cards" USING "btree" ("sold_by_user_id");



CREATE INDEX "idx_sim_cards_status" ON "public"."sim_cards" USING "btree" ("status");



CREATE INDEX "idx_sim_cards_team_id" ON "public"."sim_cards" USING "btree" ("team_id");



CREATE INDEX "idx_sim_sale_date" ON "public"."sim_cards" USING "btree" ("sale_date");



CREATE INDEX "idx_sim_serial" ON "public"."sim_cards" USING "btree" ("serial_number");



CREATE INDEX "idx_sim_status" ON "public"."sim_cards" USING "btree" ("status");



CREATE INDEX "idx_sim_team" ON "public"."sim_cards" USING "btree" ("team_id");



CREATE INDEX "idx_subscription_expires" ON "public"."subscriptions" USING "btree" ("expires_at");



CREATE INDEX "idx_subscription_status" ON "public"."subscriptions" USING "btree" ("status");



CREATE INDEX "idx_subscription_user" ON "public"."subscriptions" USING "btree" ("user_id");



CREATE INDEX "idx_task_status_created_at" ON "public"."task_status" USING "btree" ("created_at");



CREATE INDEX "idx_task_status_status" ON "public"."task_status" USING "btree" ("status");



CREATE INDEX "idx_task_status_user_id" ON "public"."task_status" USING "btree" ("user_id");



CREATE INDEX "idx_transfer_destination_team" ON "public"."sim_card_transfers" USING "btree" ("destination_team_id");



CREATE INDEX "idx_transfer_requested_by" ON "public"."sim_card_transfers" USING "btree" ("requested_by_id");



CREATE INDEX "idx_transfer_source_team" ON "public"."sim_card_transfers" USING "btree" ("source_team_id");



CREATE INDEX "idx_transfer_status" ON "public"."sim_card_transfers" USING "btree" ("status");



CREATE INDEX "idx_user_role" ON "public"."users" USING "btree" ("role");



CREATE INDEX "idx_user_team" ON "public"."users" USING "btree" ("team_id");



CREATE INDEX "notifications_created_at_idx" ON "public"."notifications" USING "btree" ("created_at" DESC);



CREATE INDEX "notifications_read_idx" ON "public"."notifications" USING "btree" ("read");



CREATE INDEX "notifications_user_id_idx" ON "public"."notifications" USING "btree" ("user_id");



CREATE OR REPLACE TRIGGER "on_deletion_request_approved" AFTER UPDATE OF "status" ON "public"."onboarding_requests" FOR EACH ROW WHEN (("new"."request_type" = 'DELETION'::"text")) EXECUTE FUNCTION "public"."handle_approved_deletion_request"();



CREATE OR REPLACE TRIGGER "on_deletion_request_insert_approved" AFTER INSERT ON "public"."onboarding_requests" FOR EACH ROW WHEN ((("new"."status" = 'APPROVED'::"text") AND ("new"."request_type" = 'DELETION'::"text"))) EXECUTE FUNCTION "public"."handle_approved_deletion_request"();



CREATE OR REPLACE TRIGGER "on_onboarding_request_approved" AFTER UPDATE OF "status" ON "public"."onboarding_requests" FOR EACH ROW EXECUTE FUNCTION "public"."handle_approved_onboarding_request"();

ALTER TABLE "public"."onboarding_requests" DISABLE TRIGGER "on_onboarding_request_approved";



CREATE OR REPLACE TRIGGER "on_onboarding_request_insert_approved" AFTER INSERT ON "public"."onboarding_requests" FOR EACH ROW WHEN (("new"."status" = 'APPROVED'::"text")) EXECUTE FUNCTION "public"."handle_approved_onboarding_request"();

ALTER TABLE "public"."onboarding_requests" DISABLE TRIGGER "on_onboarding_request_insert_approved";



CREATE OR REPLACE TRIGGER "on_sim_card_delete" AFTER DELETE ON "public"."sim_cards" FOR EACH ROW EXECUTE FUNCTION "public"."delete_batch_metadata_on_sim_delete"();



CREATE OR REPLACE TRIGGER "on_sim_card_transfer_approved" BEFORE UPDATE OF "status" ON "public"."sim_card_transfers" FOR EACH ROW EXECUTE FUNCTION "public"."handle_approved_sim_card_transfer"();



CREATE OR REPLACE TRIGGER "set_leader_team_id" AFTER INSERT ON "public"."teams" FOR EACH ROW EXECUTE FUNCTION "public"."update_user_team_id"();



CREATE OR REPLACE TRIGGER "set_leader_team_id_on_update" AFTER UPDATE ON "public"."teams" FOR EACH ROW EXECUTE FUNCTION "public"."update_leader_team_id_on_change"();



CREATE OR REPLACE TRIGGER "set_registered_on" BEFORE UPDATE ON "public"."sim_cards" FOR EACH ROW EXECUTE FUNCTION "public"."update_registered_on"();



CREATE OR REPLACE TRIGGER "set_team_admin_id_trigger" BEFORE INSERT ON "public"."teams" FOR EACH ROW EXECUTE FUNCTION "public"."set_team_admin_id"();



CREATE OR REPLACE TRIGGER "trigger_update_task_status_updated_at" BEFORE UPDATE ON "public"."task_status" FOR EACH ROW EXECUTE FUNCTION "public"."update_task_status_updated_at"();



CREATE OR REPLACE TRIGGER "update_config_updated_at" BEFORE UPDATE ON "public"."config" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_forum_posts_updated_at" BEFORE UPDATE ON "public"."forum_posts" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_forum_topics_updated_at" BEFORE UPDATE ON "public"."forum_topics" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_payment_requests_updated_at" BEFORE UPDATE ON "public"."payment_requests" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_subscription_plans_updated_at" BEFORE UPDATE ON "public"."subscription_plans" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_subscriptions_updated_at" BEFORE UPDATE ON "public"."subscriptions" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



ALTER TABLE ONLY "public"."activity_logs"
    ADD CONSTRAINT "activity_logs_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."batch_metadata"
    ADD CONSTRAINT "batch_metadata_created_by_user_id_fkey" FOREIGN KEY ("created_by_user_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."batch_metadata"
    ADD CONSTRAINT "batch_metadata_team_id_fkey" FOREIGN KEY ("team_id") REFERENCES "public"."teams"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."teams"
    ADD CONSTRAINT "fk_team_leader" FOREIGN KEY ("leader_id") REFERENCES "public"."users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."forum_likes"
    ADD CONSTRAINT "forum_likes_post_id_fkey" FOREIGN KEY ("post_id") REFERENCES "public"."forum_posts"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."forum_likes"
    ADD CONSTRAINT "forum_likes_topic_id_fkey" FOREIGN KEY ("topic_id") REFERENCES "public"."forum_topics"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."forum_likes"
    ADD CONSTRAINT "forum_likes_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."forum_likes"
    ADD CONSTRAINT "forum_likes_user_id_fkey1" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."forum_posts"
    ADD CONSTRAINT "forum_posts_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."forum_posts"
    ADD CONSTRAINT "forum_posts_created_by_fkey1" FOREIGN KEY ("created_by") REFERENCES "public"."users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."forum_posts"
    ADD CONSTRAINT "forum_posts_topic_id_fkey" FOREIGN KEY ("topic_id") REFERENCES "public"."forum_topics"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."forum_topics"
    ADD CONSTRAINT "forum_topics_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."forum_topics"
    ADD CONSTRAINT "forum_topics_created_by_fkey1" FOREIGN KEY ("created_by") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."incident_events"
    ADD CONSTRAINT "incident_events_incident_id_fkey" FOREIGN KEY ("incident_id") REFERENCES "public"."security_incidents"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."notifications"
    ADD CONSTRAINT "notifications_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."onboarding_requests"
    ADD CONSTRAINT "onboarding_requests_requested_by_id_fkey" FOREIGN KEY ("requested_by_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."onboarding_requests"
    ADD CONSTRAINT "onboarding_requests_reviewed_by_id_fkey" FOREIGN KEY ("reviewed_by_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."onboarding_requests"
    ADD CONSTRAINT "onboarding_requests_team_id_fkey" FOREIGN KEY ("team_id") REFERENCES "public"."teams"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."onboarding_requests"
    ADD CONSTRAINT "onboarding_requests_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."password_reset_requests"
    ADD CONSTRAINT "password_reset_requests_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."payment_requests"
    ADD CONSTRAINT "payment_requests_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."security_alerts"
    ADD CONSTRAINT "security_alerts_rule_id_fkey" FOREIGN KEY ("rule_id") REFERENCES "public"."alert_rules"("id");



ALTER TABLE ONLY "public"."sim_card_transfers"
    ADD CONSTRAINT "sim_card_transfers_admin_id_fkey" FOREIGN KEY ("admin_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."sim_card_transfers"
    ADD CONSTRAINT "sim_card_transfers_approved_by_id_fkey" FOREIGN KEY ("approved_by_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."sim_card_transfers"
    ADD CONSTRAINT "sim_card_transfers_destination_team_id_fkey" FOREIGN KEY ("destination_team_id") REFERENCES "public"."teams"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."sim_card_transfers"
    ADD CONSTRAINT "sim_card_transfers_requested_by_id_fkey" FOREIGN KEY ("requested_by_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."sim_card_transfers"
    ADD CONSTRAINT "sim_card_transfers_source_team_id_fkey" FOREIGN KEY ("source_team_id") REFERENCES "public"."teams"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."sim_cards"
    ADD CONSTRAINT "sim_cards_assigned_to_user_id_fkey" FOREIGN KEY ("assigned_to_user_id") REFERENCES "public"."users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."sim_cards"
    ADD CONSTRAINT "sim_cards_batch_id_fkey" FOREIGN KEY ("batch_id") REFERENCES "public"."batch_metadata"("batch_id");



ALTER TABLE ONLY "public"."sim_cards"
    ADD CONSTRAINT "sim_cards_registered_by_user_id_fkey" FOREIGN KEY ("registered_by_user_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."sim_cards"
    ADD CONSTRAINT "sim_cards_sold_by_user_id_fkey" FOREIGN KEY ("sold_by_user_id") REFERENCES "public"."users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."sim_cards"
    ADD CONSTRAINT "sim_cards_team_id_fkey" FOREIGN KEY ("team_id") REFERENCES "public"."teams"("id");



ALTER TABLE ONLY "public"."subscriptions"
    ADD CONSTRAINT "subscriptions_payment_reference_fkey" FOREIGN KEY ("payment_reference") REFERENCES "public"."payment_requests"("reference");



ALTER TABLE ONLY "public"."subscriptions"
    ADD CONSTRAINT "subscriptions_plan_id_fkey" FOREIGN KEY ("plan_id") REFERENCES "public"."subscription_plans"("id") ON DELETE SET DEFAULT;



ALTER TABLE ONLY "public"."subscriptions"
    ADD CONSTRAINT "subscriptions_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."task_status"
    ADD CONSTRAINT "task_status_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."teams"
    ADD CONSTRAINT "teams_admin_id_fkey" FOREIGN KEY ("admin_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."two_factor_verifications"
    ADD CONSTRAINT "two_factor_verifications_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."user_security_activity"
    ADD CONSTRAINT "user_security_activity_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."user_security_settings"
    ADD CONSTRAINT "user_security_settings_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."user_sessions"
    ADD CONSTRAINT "user_sessions_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."users"
    ADD CONSTRAINT "users_admin_id_fkey" FOREIGN KEY ("admin_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."users"
    ADD CONSTRAINT "users_team_id_fkey" FOREIGN KEY ("team_id") REFERENCES "public"."teams"("id");



CREATE POLICY "Admins can create batch metadata" ON "public"."batch_metadata" FOR INSERT WITH CHECK ("public"."is_admin"());



CREATE POLICY "Admins can create users" ON "public"."users" FOR INSERT WITH CHECK (("public"."is_admin"() AND ("admin_id" = "auth"."uid"())));



CREATE POLICY "Admins can delete any batch metadata" ON "public"."batch_metadata" FOR DELETE USING ("public"."is_admin"());



CREATE POLICY "Admins can manage their own teams" ON "public"."teams" USING ((("admin_id" = ( SELECT "users"."id"
   FROM "public"."users"
  WHERE (("users"."auth_user_id" = "auth"."uid"()) AND ("users"."role" = 'admin'::"text")))) OR ("public"."is_admin"() AND ("admin_id" IS NULL))));



CREATE POLICY "Admins can see SIM cards in their teams" ON "public"."sim_cards" FOR SELECT USING (((("public"."get_user_role"() = 'admin'::"text") AND ("team_id" IN ( SELECT "get_administered_team_ids"."get_administered_team_ids"
   FROM "public"."get_administered_team_ids"() "get_administered_team_ids"("get_administered_team_ids")))) OR "public"."is_leader_of_team"("team_id") OR ("sold_by_user_id" = "public"."get_user_id"())));



CREATE POLICY "Admins can see all transfer requests" ON "public"."sim_card_transfers" FOR SELECT USING ("public"."is_admin"());



CREATE POLICY "Admins can see batch metadata for their teams" ON "public"."batch_metadata" FOR SELECT USING (((("public"."get_user_role"() = 'admin'::"text") AND ("team_id" IN ( SELECT "get_administered_team_ids"."get_administered_team_ids"
   FROM "public"."get_administered_team_ids"() "get_administered_team_ids"("get_administered_team_ids")))) OR "public"."is_leader_of_team"("team_id") OR ("created_by_user_id" = "public"."get_user_id"())));



CREATE POLICY "Admins can see onboarding requests for their teams" ON "public"."onboarding_requests" FOR SELECT USING (("public"."is_admin"() AND ("admin_id" = "auth"."uid"())));



CREATE POLICY "Admins can see themselves" ON "public"."users" FOR SELECT USING (("public"."is_admin"() AND ("auth_user_id" = "auth"."uid"())));



CREATE POLICY "Admins can see users in their hierarchy" ON "public"."users" FOR SELECT USING ((("public"."is_admin"() AND ("admin_id" = "auth"."uid"())) OR ("auth_user_id" = "auth"."uid"())));



CREATE POLICY "Admins can udate them or there  user details" ON "public"."users" FOR UPDATE USING ((("id" = "public"."get_user_id"()) OR (("public"."get_user_role"() = 'admin'::"text") AND ("admin_id" = "public"."get_user_id"())))) WITH CHECK ((("id" = "public"."get_user_id"()) OR (("public"."get_user_role"() = 'admin'::"text") AND ("admin_id" = "public"."get_user_id"()))));



CREATE POLICY "Admins can update any batch metadata" ON "public"."batch_metadata" FOR UPDATE USING ("public"."is_admin"());



CREATE POLICY "Admins can update onboarding requests" ON "public"."onboarding_requests" FOR UPDATE USING (("public"."is_admin"() AND ("admin_id" = "auth"."uid"())));



CREATE POLICY "Admins can update subscriptions for their teams" ON "public"."subscriptions" FOR UPDATE USING ((("public"."get_user_role"() = 'admin'::"text") AND ("user_id" IN ( SELECT "users"."id"
   FROM "public"."users"
  WHERE ("users"."team_id" IN ( SELECT "get_administered_team_ids"."get_administered_team_ids"
           FROM "public"."get_administered_team_ids"() "get_administered_team_ids"("get_administered_team_ids")))))));



CREATE POLICY "Admins can view activity logs for their teams" ON "public"."activity_logs" FOR SELECT USING (((("public"."get_user_role"() = 'admin'::"text") AND ("user_id" IN ( SELECT "users"."id"
   FROM "public"."users"
  WHERE ("users"."team_id" IN ( SELECT "get_administered_team_ids"."get_administered_team_ids"
           FROM "public"."get_administered_team_ids"() "get_administered_team_ids"("get_administered_team_ids")))))) OR ("user_id" = "public"."get_user_id"())));



CREATE POLICY "All authenticated users can view teams" ON "public"."teams" FOR SELECT TO "authenticated" USING (true);



CREATE POLICY "All can update" ON "public"."users" FOR UPDATE USING (true) WITH CHECK (true);



CREATE POLICY "Any can update" ON "public"."sim_cards" FOR UPDATE USING (true) WITH CHECK (true);



CREATE POLICY "Service role full access" ON "public"."detection_rules" USING (("auth"."role"() = 'service_role'::"text"));



CREATE POLICY "Service role full access" ON "public"."incident_events" USING (("auth"."role"() = 'service_role'::"text"));



CREATE POLICY "Service role full access" ON "public"."ip_blocks" USING (("auth"."role"() = 'service_role'::"text"));



CREATE POLICY "Service role full access" ON "public"."ip_intelligence" USING (("auth"."role"() = 'service_role'::"text"));



CREATE POLICY "Service role full access" ON "public"."security_alerts" USING (("auth"."role"() = 'service_role'::"text"));



CREATE POLICY "Service role full access" ON "public"."security_incidents" USING (("auth"."role"() = 'service_role'::"text"));



CREATE POLICY "Service role full access" ON "public"."security_request_logs" USING (("auth"."role"() = 'service_role'::"text"));



CREATE POLICY "Staff can create SIM cards" ON "public"."sim_cards" FOR INSERT TO "authenticated" WITH CHECK (("public"."is_admin"() OR (("public"."is_team_leader"() OR ("public"."get_user_id"() IN ( SELECT "users"."id"
   FROM "public"."users"
  WHERE ("users"."role" = 'staff'::"text")))) AND ("sold_by_user_id" = "public"."get_user_id"()))));



CREATE POLICY "Staff can create batch metadata" ON "public"."batch_metadata" FOR INSERT WITH CHECK ((("created_by_user_id" = "public"."get_user_id"()) AND ("team_id" = "public"."get_user_team_id"())));



CREATE POLICY "Staff can delete batch metadata they created" ON "public"."batch_metadata" FOR DELETE USING (("created_by_user_id" = "public"."get_user_id"()));



CREATE POLICY "Staff can see batch metadata they created" ON "public"."batch_metadata" FOR SELECT USING (("created_by_user_id" = "public"."get_user_id"()));



CREATE POLICY "Staff can see simcards" ON "public"."sim_cards" FOR SELECT USING (true);



CREATE POLICY "Staff can update batch metadata they created" ON "public"."batch_metadata" FOR UPDATE USING (("created_by_user_id" = "public"."get_user_id"()));



CREATE POLICY "Staff can update their own SIM cards" ON "public"."sim_cards" FOR UPDATE TO "authenticated" USING ((("assigned_to_user_id" = "public"."get_user_id"()) OR "public"."is_admin"() OR "public"."is_leader_of_team"("team_id")));



CREATE POLICY "System can insert and update user sessions" ON "public"."user_sessions" FOR INSERT WITH CHECK (true);



CREATE POLICY "System can insert password reset requests" ON "public"."password_reset_requests" FOR INSERT WITH CHECK (true);



CREATE POLICY "System can insert user security activity" ON "public"."user_security_activity" FOR INSERT WITH CHECK (true);



CREATE POLICY "System can insert verifications" ON "public"."two_factor_verifications" FOR INSERT WITH CHECK (true);



CREATE POLICY "System can update password reset requests" ON "public"."password_reset_requests" FOR UPDATE USING (true);



CREATE POLICY "System can update user security activity" ON "public"."user_security_activity" FOR UPDATE USING (true);



CREATE POLICY "System can update user sessions" ON "public"."user_sessions" FOR UPDATE USING (true);



CREATE POLICY "System can update verifications" ON "public"."two_factor_verifications" FOR UPDATE USING (true);



CREATE POLICY "Team leaders can create batch metadata for their team" ON "public"."batch_metadata" FOR INSERT WITH CHECK (("public"."is_leader_of_team"("team_id") OR ("public"."is_team_leader"() AND ("team_id" = "public"."get_user_team_id"()))));



CREATE POLICY "Team leaders can create onboarding requests" ON "public"."onboarding_requests" FOR INSERT TO "authenticated" WITH CHECK ("public"."is_team_leader"());



CREATE POLICY "Team leaders can create transfer requests" ON "public"."sim_card_transfers" FOR INSERT WITH CHECK (("public"."is_team_leader"() AND "public"."is_leader_of_team"("source_team_id")));



CREATE POLICY "Team leaders can delete their team's batch metadata" ON "public"."batch_metadata" FOR DELETE USING ("public"."is_leader_of_team"("team_id"));



CREATE POLICY "Team leaders can delete there  onboarding requests" ON "public"."onboarding_requests" FOR DELETE TO "authenticated" USING (("requested_by_id" = "auth"."uid"()));



CREATE POLICY "Team leaders can see their own onboarding requests" ON "public"."onboarding_requests" FOR SELECT USING ((("requested_by_id" = "public"."get_user_id"()) OR "public"."is_leader_of_team"("team_id")));



CREATE POLICY "Team leaders can see their own transfer requests" ON "public"."sim_card_transfers" FOR SELECT USING (("public"."is_leader_of_team"("source_team_id") OR "public"."is_leader_of_team"("destination_team_id")));



CREATE POLICY "Team leaders can see their team members" ON "public"."users" FOR SELECT USING (("public"."is_leader_of_team"("team_id") OR ("auth_user_id" = "auth"."uid"())));



CREATE POLICY "Team leaders can see their team's SIM cards" ON "public"."sim_cards" FOR SELECT USING ("public"."is_leader_of_team"("team_id"));



CREATE POLICY "Team leaders can see their team's batch metadata" ON "public"."batch_metadata" FOR SELECT USING ("public"."is_leader_of_team"("team_id"));



CREATE POLICY "Team leaders can update their team's batch metadata" ON "public"."batch_metadata" FOR UPDATE USING ("public"."is_leader_of_team"("team_id"));



CREATE POLICY "Users can create their own activity logs" ON "public"."activity_logs" FOR INSERT TO "authenticated" WITH CHECK (("user_id" = "public"."get_user_id"()));



CREATE POLICY "Users can create their own subscriptions" ON "public"."subscriptions" FOR INSERT WITH CHECK (("user_id" = "public"."get_user_id"()));



CREATE POLICY "Users can delete their own sessions" ON "public"."user_sessions" FOR DELETE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can insert their own security settings" ON "public"."user_security_settings" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can see related subscription" ON "public"."payment_requests" FOR SELECT USING ((("public"."is_admin"() AND ("user_id" = "auth"."uid"())) OR ("user_id" = ( SELECT "users"."admin_id"
   FROM "public"."users"
  WHERE ("auth"."uid"() = "users"."id")))));



CREATE POLICY "Users can see themselves" ON "public"."users" FOR SELECT USING (("auth_user_id" = "auth"."uid"()));



CREATE POLICY "Users can update their own notifications" ON "public"."notifications" FOR UPDATE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can update their own security settings" ON "public"."user_security_settings" FOR UPDATE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can update their own subscriptions" ON "public"."subscriptions" FOR UPDATE USING (("user_id" = "public"."get_user_id"()));



CREATE POLICY "Users can view their own activity logs" ON "public"."activity_logs" FOR SELECT USING (("user_id" = "public"."get_user_id"()));



CREATE POLICY "Users can view their own notifications" ON "public"."notifications" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can view their own reset requests" ON "public"."password_reset_requests" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can view their own security activity" ON "public"."user_security_activity" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can view their own security settings" ON "public"."user_security_settings" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can view their own sessions" ON "public"."user_sessions" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can view their own verifications" ON "public"."two_factor_verifications" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users see Related subscription" ON "public"."subscriptions" FOR SELECT USING ((("public"."is_admin"() AND ("user_id" = "auth"."uid"())) OR ("user_id" = ( SELECT "users"."admin_id"
   FROM "public"."users"
  WHERE ("auth"."uid"() = "users"."id")))));



ALTER TABLE "public"."activity_logs" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "admin can delete" ON "public"."users" FOR DELETE TO "authenticated" USING (("public"."is_admin"() AND ("admin_id" = "auth"."uid"())));



CREATE POLICY "all" ON "public"."sim_cards" FOR DELETE USING (true);



CREATE POLICY "any one can create notification" ON "public"."notifications" FOR INSERT TO "authenticated" WITH CHECK (true);



ALTER TABLE "public"."batch_metadata" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."detection_rules" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."forum_likes" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "forum_likes_delete_policy" ON "public"."forum_likes" FOR DELETE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "forum_likes_insert_policy" ON "public"."forum_likes" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "forum_likes_select_policy" ON "public"."forum_likes" FOR SELECT USING (true);



ALTER TABLE "public"."forum_posts" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "forum_posts_delete_policy" ON "public"."forum_posts" FOR DELETE USING ((("auth"."uid"() = "created_by") OR (EXISTS ( SELECT 1
   FROM "public"."users"
  WHERE (("users"."id" = "auth"."uid"()) AND ("users"."role" = 'admin'::"text"))))));



CREATE POLICY "forum_posts_insert_policy" ON "public"."forum_posts" FOR INSERT WITH CHECK (("auth"."uid"() = "created_by"));



CREATE POLICY "forum_posts_select_policy" ON "public"."forum_posts" FOR SELECT USING (true);



CREATE POLICY "forum_posts_update_policy" ON "public"."forum_posts" FOR UPDATE USING ((("auth"."uid"() = "created_by") OR (EXISTS ( SELECT 1
   FROM "public"."users"
  WHERE (("users"."id" = "auth"."uid"()) AND ("users"."role" = 'admin'::"text"))))));



ALTER TABLE "public"."forum_topics" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "forum_topics_delete_policy" ON "public"."forum_topics" FOR DELETE USING ((("auth"."uid"() = "created_by") OR (EXISTS ( SELECT 1
   FROM "public"."users"
  WHERE (("users"."id" = "auth"."uid"()) AND ("users"."role" = 'admin'::"text"))))));



CREATE POLICY "forum_topics_insert_policy" ON "public"."forum_topics" FOR INSERT WITH CHECK (("auth"."uid"() = "created_by"));



CREATE POLICY "forum_topics_select_policy" ON "public"."forum_topics" FOR SELECT USING (true);



CREATE POLICY "forum_topics_update_policy" ON "public"."forum_topics" FOR UPDATE USING ((("auth"."uid"() = "created_by") OR (EXISTS ( SELECT 1
   FROM "public"."users"
  WHERE (("users"."id" = "auth"."uid"()) AND ("users"."role" = 'admin'::"text"))))));



ALTER TABLE "public"."incident_events" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."ip_blocks" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."ip_intelligence" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."notifications" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."onboarding_requests" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."password_reset_requests" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."payment_requests" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."security_alerts" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."security_incidents" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."security_request_logs" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."sim_card_transfers" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."sim_cards" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."subscriptions" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."task_status" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "task_status_user_policy" ON "public"."task_status" USING (("auth"."uid"() = "user_id"));



ALTER TABLE "public"."teams" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."two_factor_verifications" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "user exists" ON "public"."users" FOR SELECT USING (true);



ALTER TABLE "public"."user_security_activity" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."user_security_settings" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."user_sessions" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."users" ENABLE ROW LEVEL SECURITY;




ALTER PUBLICATION "supabase_realtime" OWNER TO "postgres";






ALTER PUBLICATION "supabase_realtime" ADD TABLE ONLY "public"."activity_logs";



ALTER PUBLICATION "supabase_realtime" ADD TABLE ONLY "public"."notifications";



ALTER PUBLICATION "supabase_realtime" ADD TABLE ONLY "public"."onboarding_requests";



ALTER PUBLICATION "supabase_realtime" ADD TABLE ONLY "public"."sim_cards";



ALTER PUBLICATION "supabase_realtime" ADD TABLE ONLY "public"."users";






GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";
































































































































































































GRANT ALL ON FUNCTION "public"."aggregate_hourly_metrics"() TO "anon";
GRANT ALL ON FUNCTION "public"."aggregate_hourly_metrics"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."aggregate_hourly_metrics"() TO "service_role";



GRANT ALL ON TABLE "public"."users" TO "anon";
GRANT ALL ON TABLE "public"."users" TO "authenticated";
GRANT ALL ON TABLE "public"."users" TO "service_role";



GRANT ALL ON FUNCTION "public"."bypass_rls_get_user"("user_auth_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."bypass_rls_get_user"("user_auth_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."bypass_rls_get_user"("user_auth_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."calculate_risk_score"("threat_level" character varying, "signature_matches" "text"[], "behavioral_flags" "text"[], "anomaly_score" numeric, "ip_reputation" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."calculate_risk_score"("threat_level" character varying, "signature_matches" "text"[], "behavioral_flags" "text"[], "anomaly_score" numeric, "ip_reputation" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."calculate_risk_score"("threat_level" character varying, "signature_matches" "text"[], "behavioral_flags" "text"[], "anomaly_score" numeric, "ip_reputation" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."cleanup_expired_sessions"() TO "anon";
GRANT ALL ON FUNCTION "public"."cleanup_expired_sessions"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."cleanup_expired_sessions"() TO "service_role";



GRANT ALL ON FUNCTION "public"."delete_batch_metadata_on_sim_delete"() TO "anon";
GRANT ALL ON FUNCTION "public"."delete_batch_metadata_on_sim_delete"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."delete_batch_metadata_on_sim_delete"() TO "service_role";



GRANT ALL ON FUNCTION "public"."delete_team_with_dependencies"("team_id_param" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."delete_team_with_dependencies"("team_id_param" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."delete_team_with_dependencies"("team_id_param" "uuid") TO "service_role";



GRANT ALL ON PROCEDURE "public"."delete_user_and_dependants"(IN "target_user_id" "uuid") TO "anon";
GRANT ALL ON PROCEDURE "public"."delete_user_and_dependants"(IN "target_user_id" "uuid") TO "authenticated";
GRANT ALL ON PROCEDURE "public"."delete_user_and_dependants"(IN "target_user_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."get_accessible_user_ids"() TO "anon";
GRANT ALL ON FUNCTION "public"."get_accessible_user_ids"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_accessible_user_ids"() TO "service_role";



GRANT ALL ON FUNCTION "public"."get_administered_team_ids"() TO "anon";
GRANT ALL ON FUNCTION "public"."get_administered_team_ids"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_administered_team_ids"() TO "service_role";



GRANT ALL ON FUNCTION "public"."get_batches_with_counts"("user_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."get_batches_with_counts"("user_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_batches_with_counts"("user_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."get_comprehensive_security_metrics"() TO "anon";
GRANT ALL ON FUNCTION "public"."get_comprehensive_security_metrics"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_comprehensive_security_metrics"() TO "service_role";



GRANT ALL ON FUNCTION "public"."get_geographic_threat_distribution"() TO "anon";
GRANT ALL ON FUNCTION "public"."get_geographic_threat_distribution"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_geographic_threat_distribution"() TO "service_role";



GRANT ALL ON FUNCTION "public"."get_my_team_admin_id"() TO "anon";
GRANT ALL ON FUNCTION "public"."get_my_team_admin_id"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_my_team_admin_id"() TO "service_role";



GRANT ALL ON FUNCTION "public"."get_team_hierarchy"("in_team_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."get_team_hierarchy"("in_team_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_team_hierarchy"("in_team_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."get_threat_timeline"("hours_back" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."get_threat_timeline"("hours_back" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_threat_timeline"("hours_back" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_top_attacking_ips"("limit_count" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."get_top_attacking_ips"("limit_count" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_top_attacking_ips"("limit_count" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_user_id"() TO "anon";
GRANT ALL ON FUNCTION "public"."get_user_id"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_user_id"() TO "service_role";



GRANT ALL ON FUNCTION "public"."get_user_role"() TO "anon";
GRANT ALL ON FUNCTION "public"."get_user_role"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_user_role"() TO "service_role";



GRANT ALL ON FUNCTION "public"."get_user_role_safe"() TO "anon";
GRANT ALL ON FUNCTION "public"."get_user_role_safe"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_user_role_safe"() TO "service_role";



GRANT ALL ON FUNCTION "public"."get_user_team_id"() TO "anon";
GRANT ALL ON FUNCTION "public"."get_user_team_id"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_user_team_id"() TO "service_role";



GRANT ALL ON FUNCTION "public"."handle_approved_deletion_request"() TO "anon";
GRANT ALL ON FUNCTION "public"."handle_approved_deletion_request"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."handle_approved_deletion_request"() TO "service_role";



GRANT ALL ON FUNCTION "public"."handle_approved_onboarding_request"() TO "anon";
GRANT ALL ON FUNCTION "public"."handle_approved_onboarding_request"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."handle_approved_onboarding_request"() TO "service_role";



GRANT ALL ON FUNCTION "public"."handle_approved_sim_card_transfer"() TO "anon";
GRANT ALL ON FUNCTION "public"."handle_approved_sim_card_transfer"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."handle_approved_sim_card_transfer"() TO "service_role";



GRANT ALL ON FUNCTION "public"."has_access_to_user"("target_user_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."has_access_to_user"("target_user_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."has_access_to_user"("target_user_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."is_admin"() TO "anon";
GRANT ALL ON FUNCTION "public"."is_admin"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."is_admin"() TO "service_role";



GRANT ALL ON FUNCTION "public"."is_admin_for_team"("team_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."is_admin_for_team"("team_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."is_admin_for_team"("team_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."is_leader_of_team"("team_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."is_leader_of_team"("team_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."is_leader_of_team"("team_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."is_member_of_team"("team_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."is_member_of_team"("team_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."is_member_of_team"("team_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."is_team_leader"() TO "anon";
GRANT ALL ON FUNCTION "public"."is_team_leader"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."is_team_leader"() TO "service_role";



GRANT ALL ON FUNCTION "public"."register_user_session"() TO "anon";
GRANT ALL ON FUNCTION "public"."register_user_session"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."register_user_session"() TO "service_role";



GRANT ALL ON TABLE "public"."sim_cards" TO "anon";
GRANT ALL ON TABLE "public"."sim_cards" TO "authenticated";
GRANT ALL ON TABLE "public"."sim_cards" TO "service_role";



GRANT ALL ON FUNCTION "public"."search_sim_cards"("search_term" "text", "status_filter" "text", "team_id_param" "uuid", "from_date" timestamp without time zone, "to_date" timestamp without time zone) TO "anon";
GRANT ALL ON FUNCTION "public"."search_sim_cards"("search_term" "text", "status_filter" "text", "team_id_param" "uuid", "from_date" timestamp without time zone, "to_date" timestamp without time zone) TO "authenticated";
GRANT ALL ON FUNCTION "public"."search_sim_cards"("search_term" "text", "status_filter" "text", "team_id_param" "uuid", "from_date" timestamp without time zone, "to_date" timestamp without time zone) TO "service_role";



GRANT ALL ON FUNCTION "public"."search_sim_cards"("search_term" "text", "status_filter" "text", "team_id" "uuid", "from_date" timestamp with time zone, "to_date" timestamp with time zone) TO "anon";
GRANT ALL ON FUNCTION "public"."search_sim_cards"("search_term" "text", "status_filter" "text", "team_id" "uuid", "from_date" timestamp with time zone, "to_date" timestamp with time zone) TO "authenticated";
GRANT ALL ON FUNCTION "public"."search_sim_cards"("search_term" "text", "status_filter" "text", "team_id" "uuid", "from_date" timestamp with time zone, "to_date" timestamp with time zone) TO "service_role";



GRANT ALL ON FUNCTION "public"."set_team_admin_id"() TO "anon";
GRANT ALL ON FUNCTION "public"."set_team_admin_id"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."set_team_admin_id"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_leader_team_id_on_change"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_leader_team_id_on_change"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_leader_team_id_on_change"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_registered_on"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_registered_on"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_registered_on"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_task_status_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_task_status_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_task_status_updated_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_user_team_id"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_user_team_id"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_user_team_id"() TO "service_role";
























GRANT ALL ON TABLE "public"."activity_logs" TO "anon";
GRANT ALL ON TABLE "public"."activity_logs" TO "authenticated";
GRANT ALL ON TABLE "public"."activity_logs" TO "service_role";



GRANT ALL ON TABLE "public"."alert_rules" TO "anon";
GRANT ALL ON TABLE "public"."alert_rules" TO "authenticated";
GRANT ALL ON TABLE "public"."alert_rules" TO "service_role";



GRANT ALL ON TABLE "public"."batch_metadata" TO "anon";
GRANT ALL ON TABLE "public"."batch_metadata" TO "authenticated";
GRANT ALL ON TABLE "public"."batch_metadata" TO "service_role";



GRANT ALL ON TABLE "public"."config" TO "anon";
GRANT ALL ON TABLE "public"."config" TO "authenticated";
GRANT ALL ON TABLE "public"."config" TO "service_role";



GRANT ALL ON TABLE "public"."detection_rules" TO "anon";
GRANT ALL ON TABLE "public"."detection_rules" TO "authenticated";
GRANT ALL ON TABLE "public"."detection_rules" TO "service_role";



GRANT ALL ON TABLE "public"."forum_likes" TO "anon";
GRANT ALL ON TABLE "public"."forum_likes" TO "authenticated";
GRANT ALL ON TABLE "public"."forum_likes" TO "service_role";



GRANT ALL ON TABLE "public"."forum_posts" TO "anon";
GRANT ALL ON TABLE "public"."forum_posts" TO "authenticated";
GRANT ALL ON TABLE "public"."forum_posts" TO "service_role";



GRANT ALL ON TABLE "public"."forum_topics" TO "anon";
GRANT ALL ON TABLE "public"."forum_topics" TO "authenticated";
GRANT ALL ON TABLE "public"."forum_topics" TO "service_role";



GRANT ALL ON TABLE "public"."public_user_profiles" TO "anon";
GRANT ALL ON TABLE "public"."public_user_profiles" TO "authenticated";
GRANT ALL ON TABLE "public"."public_user_profiles" TO "service_role";



GRANT ALL ON TABLE "public"."forum_topics_with_author" TO "anon";
GRANT ALL ON TABLE "public"."forum_topics_with_author" TO "authenticated";
GRANT ALL ON TABLE "public"."forum_topics_with_author" TO "service_role";



GRANT ALL ON TABLE "public"."security_request_logs" TO "anon";
GRANT ALL ON TABLE "public"."security_request_logs" TO "authenticated";
GRANT ALL ON TABLE "public"."security_request_logs" TO "service_role";



GRANT ALL ON TABLE "public"."geographic_threat_distribution" TO "anon";
GRANT ALL ON TABLE "public"."geographic_threat_distribution" TO "authenticated";
GRANT ALL ON TABLE "public"."geographic_threat_distribution" TO "service_role";



GRANT ALL ON TABLE "public"."incident_events" TO "anon";
GRANT ALL ON TABLE "public"."incident_events" TO "authenticated";
GRANT ALL ON TABLE "public"."incident_events" TO "service_role";



GRANT ALL ON TABLE "public"."ip_blocks" TO "anon";
GRANT ALL ON TABLE "public"."ip_blocks" TO "authenticated";
GRANT ALL ON TABLE "public"."ip_blocks" TO "service_role";



GRANT ALL ON TABLE "public"."ip_intelligence" TO "anon";
GRANT ALL ON TABLE "public"."ip_intelligence" TO "authenticated";
GRANT ALL ON TABLE "public"."ip_intelligence" TO "service_role";



GRANT ALL ON TABLE "public"."notifications" TO "anon";
GRANT ALL ON TABLE "public"."notifications" TO "authenticated";
GRANT ALL ON TABLE "public"."notifications" TO "service_role";



GRANT ALL ON TABLE "public"."onboarding_requests" TO "anon";
GRANT ALL ON TABLE "public"."onboarding_requests" TO "authenticated";
GRANT ALL ON TABLE "public"."onboarding_requests" TO "service_role";



GRANT ALL ON TABLE "public"."password_reset_requests" TO "anon";
GRANT ALL ON TABLE "public"."password_reset_requests" TO "authenticated";
GRANT ALL ON TABLE "public"."password_reset_requests" TO "service_role";



GRANT ALL ON TABLE "public"."payment_requests" TO "anon";
GRANT ALL ON TABLE "public"."payment_requests" TO "authenticated";
GRANT ALL ON TABLE "public"."payment_requests" TO "service_role";



GRANT ALL ON TABLE "public"."real_time_threat_overview" TO "anon";
GRANT ALL ON TABLE "public"."real_time_threat_overview" TO "authenticated";
GRANT ALL ON TABLE "public"."real_time_threat_overview" TO "service_role";



GRANT ALL ON TABLE "public"."security_alerts" TO "anon";
GRANT ALL ON TABLE "public"."security_alerts" TO "authenticated";
GRANT ALL ON TABLE "public"."security_alerts" TO "service_role";



GRANT ALL ON TABLE "public"."security_config" TO "anon";
GRANT ALL ON TABLE "public"."security_config" TO "authenticated";
GRANT ALL ON TABLE "public"."security_config" TO "service_role";



GRANT ALL ON TABLE "public"."security_incidents" TO "anon";
GRANT ALL ON TABLE "public"."security_incidents" TO "authenticated";
GRANT ALL ON TABLE "public"."security_incidents" TO "service_role";



GRANT ALL ON TABLE "public"."security_metrics_daily" TO "anon";
GRANT ALL ON TABLE "public"."security_metrics_daily" TO "authenticated";
GRANT ALL ON TABLE "public"."security_metrics_daily" TO "service_role";



GRANT ALL ON SEQUENCE "public"."security_metrics_daily_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."security_metrics_daily_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."security_metrics_daily_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."security_metrics_hourly" TO "anon";
GRANT ALL ON TABLE "public"."security_metrics_hourly" TO "authenticated";
GRANT ALL ON TABLE "public"."security_metrics_hourly" TO "service_role";



GRANT ALL ON SEQUENCE "public"."security_metrics_hourly_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."security_metrics_hourly_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."security_metrics_hourly_id_seq" TO "service_role";



GRANT ALL ON SEQUENCE "public"."security_request_logs_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."security_request_logs_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."security_request_logs_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."sim_card_transfers" TO "anon";
GRANT ALL ON TABLE "public"."sim_card_transfers" TO "authenticated";
GRANT ALL ON TABLE "public"."sim_card_transfers" TO "service_role";



GRANT ALL ON TABLE "public"."teams" TO "anon";
GRANT ALL ON TABLE "public"."teams" TO "authenticated";
GRANT ALL ON TABLE "public"."teams" TO "service_role";



GRANT ALL ON TABLE "public"."staff_performance" TO "anon";
GRANT ALL ON TABLE "public"."staff_performance" TO "authenticated";
GRANT ALL ON TABLE "public"."staff_performance" TO "service_role";



GRANT ALL ON TABLE "public"."subscription_plans" TO "anon";
GRANT ALL ON TABLE "public"."subscription_plans" TO "authenticated";
GRANT ALL ON TABLE "public"."subscription_plans" TO "service_role";



GRANT ALL ON TABLE "public"."subscriptions" TO "anon";
GRANT ALL ON TABLE "public"."subscriptions" TO "authenticated";
GRANT ALL ON TABLE "public"."subscriptions" TO "service_role";



GRANT ALL ON TABLE "public"."subscription_status" TO "anon";
GRANT ALL ON TABLE "public"."subscription_status" TO "authenticated";
GRANT ALL ON TABLE "public"."subscription_status" TO "service_role";



GRANT ALL ON TABLE "public"."task_status" TO "anon";
GRANT ALL ON TABLE "public"."task_status" TO "authenticated";
GRANT ALL ON TABLE "public"."task_status" TO "service_role";



GRANT ALL ON TABLE "public"."team_performance" TO "anon";
GRANT ALL ON TABLE "public"."team_performance" TO "authenticated";
GRANT ALL ON TABLE "public"."team_performance" TO "service_role";



GRANT ALL ON TABLE "public"."top_attacking_ips" TO "anon";
GRANT ALL ON TABLE "public"."top_attacking_ips" TO "authenticated";
GRANT ALL ON TABLE "public"."top_attacking_ips" TO "service_role";



GRANT ALL ON TABLE "public"."two_factor_verifications" TO "anon";
GRANT ALL ON TABLE "public"."two_factor_verifications" TO "authenticated";
GRANT ALL ON TABLE "public"."two_factor_verifications" TO "service_role";



GRANT ALL ON TABLE "public"."user_security_activity" TO "anon";
GRANT ALL ON TABLE "public"."user_security_activity" TO "authenticated";
GRANT ALL ON TABLE "public"."user_security_activity" TO "service_role";



GRANT ALL ON TABLE "public"."user_security_settings" TO "anon";
GRANT ALL ON TABLE "public"."user_security_settings" TO "authenticated";
GRANT ALL ON TABLE "public"."user_security_settings" TO "service_role";



GRANT ALL ON TABLE "public"."user_sessions" TO "anon";
GRANT ALL ON TABLE "public"."user_sessions" TO "authenticated";
GRANT ALL ON TABLE "public"."user_sessions" TO "service_role";









ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES  TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES  TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES  TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES  TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS  TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS  TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS  TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS  TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES  TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES  TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES  TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES  TO "service_role";






























RESET ALL;
