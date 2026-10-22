from django.db import migrations

# Последний рубеж для инварианта «short_code никогда не меняется»: ловит и то,
# что обходит Memorial.save() (QuerySet.update, raw SQL).
CREATE_TRIGGER = """
CREATE FUNCTION memorials_short_code_immutable() RETURNS trigger AS $$
BEGIN
    IF NEW.short_code IS DISTINCT FROM OLD.short_code THEN
        RAISE EXCEPTION 'memorials_memorial.short_code is immutable'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER memorials_short_code_immutable
    BEFORE UPDATE OF short_code ON memorials_memorial
    FOR EACH ROW EXECUTE FUNCTION memorials_short_code_immutable();
"""

DROP_TRIGGER = """
DROP TRIGGER IF EXISTS memorials_short_code_immutable ON memorials_memorial;
DROP FUNCTION IF EXISTS memorials_short_code_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("memorials", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(CREATE_TRIGGER, reverse_sql=DROP_TRIGGER),
    ]
