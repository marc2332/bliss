from warnings import warn

warn('\nKhoros plugin is deprecated and will be removed soon. Use bliss plugin instead.',  FutureWarning)

from .bliss import create_objects_from_config_node

