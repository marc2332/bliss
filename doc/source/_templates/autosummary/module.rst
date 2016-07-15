.. py:currentmodule:: {{ fullname }}

{{ fullname }}
{{ underline }}
{% if module %}
(parent module: :mod:`{{ module }}`)
{% endif %}
.. automodule:: {{ fullname }}
   {% if functions or classes or exceptions %}
   {% block functions %} {% if functions %}
   **Functions**

   .. autosummary::
   {% for item in functions %}
      ~{{ fullname }}.{{ item }}
   {% endfor %}
   {% endif %} {% endblock %}
   {% block classes %} {% if classes %}

   **Classes**

   .. autosummary::
   {% for item in classes %}
      ~{{ fullname }}.{{ item }}
   {% endfor %}
   {% endif %} {% endblock %}
   {% block exceptions %} {% if exceptions %}

   **Exceptions**

   .. autosummary::
   {% for item in exceptions %}
      ~{{ fullname }}.{{ item }}
   {% endfor %}
   {% endif %} {% endblock %}

   .. rubric:: Details
   {% if functions %}

   **Functions**

   {% for item in functions %}
   .. autofunction:: {{ item }}

   {% endfor %} {% endif %}
   {% if classes %}

   **Classes**
   {% for item in classes %}

   .. autoclass:: {{ item }}
      :members:
      :undoc-members:
   {% endfor %} {% endif %}
   {% if exceptions %}

   **Exceptions**
   {% for item in exceptions %}

   .. autoexception:: {{ item }}
   {% endfor %} {% endif %} {% endif %}
