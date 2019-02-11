# Beacon channels

*Channels* use the built-in [publish/subscribe features of Redis](https://redis.io/topics/pubsub)
in order to provide a simple way to exchange data between different BLISS processes.

Contrary to Settings, channels data is **not persisted**. When the last
client holding the data disconnects, the channel data is cleared.

Use cases for channels are:

* to update state between processes
    - for example, for `Axis` objects, `position` and `state` (`MOVING`, `READY`...) are shared between listeners
* caching for performance, e.g. to avoid reloading
    - to memorize last loaded program in a MUSST or Opiom
    - to memorize MCA parameters
* to prevent unwanted hardware initialization
    - if an object is shared between multiple processes, is in use and is already initialized, there is no need (it can even be harmful) to re-initialize it

## `Channel` object usage

Process A:

```py
>>> from bliss.config.channels import Channel
>>> c = Channel("test", default_value=42)
>>> c.value
42
```

Process B:

```py
>>> from bliss.config.channels import Channel
>>> c = Channel("test")
>>> c.value
42
```

It is possible to register a callback to get notified of Channel value change events:

```py
# in process A
>>> def c_value_changed(new_value):
        print(new_value)
>>> c.register_callback(c_value_changed)
```

```py
# in process B
>>> c.value = "something new"

# in process A, output:
something new
```

## `Cache` object

A Cache object is a helper to make a Channel attached to an object from the
configuration. It guarantees the name of the channel corresponds to the
object, by pre-pending the name of the object to the corresponding key in Redis.

```py
>>> from bliss.config.static import get_config
>>> config = get_config()
>>> obj = config.get("my_object")
>>> from bliss.config.channels import Cache
>>> cached_value = Cache(obj, "my_cached_value", default_value="X")
# the cached_value object is a Channel
>>> cached_value.value = "something"
```

The `clear_cache(*devices)` function from `bliss.config.channels` deletes all
cached values for the list of devices provided as function arguments.

!!! note
    When the last client holding a channel disconnects, the channel is
    removed. It is cleared from Redis. In case another channel with the same
    name is created afterwards, reading it returns the default value.
