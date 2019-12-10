from nexus_writer_service import metadata

# Needed for the tests that do not use the tango server (SCAN_SAVING.writer != "nexus")
metadata.register_all_metadata_generators()
