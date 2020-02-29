# Groups of scans and sequences

Bliss provides the capability to bundle several scans together into a group or a sequence.

## Groups

Groups can be used to bundle scans **after** they have run.

!!! example

    ```python
	BLISS [3]: from bliss.scanning.group import Group
	      ...: diode=config.get('diode')
	      ...: s1=loopscan(3,.1,diode)
	      ...: s2=loopscan(3,.2,diode)
	      ...: Group(s1,s2)
    ```

The `Group` command takes as keyword arguments `title` and `scan_info`. Scans can be added to a group via their Scan object (`bliss.scanning.scan.Scan`, like in the example above), via the corresponding Scan data node (`bliss.data.scan.Scan`) or simply via their scan number. Please note that the scan has still to be in memory (redis) in order for this mechanism to work.

## Sequences
Sequences can be used to bundle scans no matter if they have alreay been exceuted before or if they will be running during the sequence. The only condition: all scans of the sequence musst terminate before leaving the context manager provied by the sequence. The `Sequences` object takes as keyword arguments `title` and `scan_info`.

!!! example
    ```python
	TEST_SESSION [4]: from bliss.scanning.group import Sequence
                 ...: seq=Sequence()
                 ...: with seq.sequence_context() as scan_seq:
                 ...:     s1=loopscan(5,.1,diode,run=False)
                 ...:     scan_seq.add(s1)
                 ...:     s1.run()
                 ...:
                 ...:     #do something here ... move motors, open/close shutter
                 ...:
                 ...:     s2=loopscan(3,.2,diode,run=False)
                 ...:     scan_seq.add_and_run(s2)
                 ...:
                 ...:     #do more things
                 ...:
                 ...:     s3=loopscan(3,.2,diode)
                 ...:     scan_seq.add(s3)
    ```

In the example above we prepare scans (s1 and s2 ... note the `run=False` keyword argument) and add them to the sequence by calling `add` or `add_and_run`. It is also possible to add a scan that has alreay terminated (s3). However, when thinking about online data analysis it is advisable to first add the scans to the sequencs and run them afterwards (like s1 and s2) as this enables external processes to follow the sequence in real time.

### Channels attached to sequences
 
It is possible to publish additional channels that are not part of any of the scans inside the sequence. These channels could e.g. be the result of a calculation based on the data acquired during the sequence.

!!! example
    ```python
	TEST_SESSION [12]: from bliss.scanning.group import Sequence
		      ...: from bliss.scanning.chain import AcquisitionChannel
		      ...: import numpy
		      ...: seq=Sequence()
		      ...: seq.add_custom_channel(AcquisitionChannel('mychannel',numpy.float,()))
		      ...: seq.add_custom_channel(AcquisitionChannel('sum',numpy.float,()))
		      ...: with seq.sequence_context() as scan_seq:
		      ...:     s1=loopscan(5,.1,diode,run=False)
		      ...:     s2=loopscan(5,.1,diode,run=False)
		      ...:     scan_seq.add_and_run(s1)
		      ...:     scan_seq.add_and_run(s2)
		      ...:
		      ...:     seq.custom_channels['mychannel'].emit([1.1,2.2,3.3])
		      ...:
		      ...:     my_sum = s1.get_data()[diode] + s2.get_data()[diode]
		      ...:     seq.custom_channels['sum'].emit(my_sum)

    ```

## Listening in redis to scan groups

The following example is listening to groups and sequences in redis:

!!! example
    ```python
	TEST_SESSION [7]: from bliss import current_session
	TEST_SESSION [8]: from bliss.data.node import get_session_node

	TEST_SESSION [9]: for node in get_session_node(current_session.name).iterator.walk(filter='scan_group',wait=False):
		     ...:     print(node.db_name,node.info["scan_nb"])
	test_session:tmp:scans:55_sequence_of_scans 55
    ```

If one wants to listen to scans and groups of scans at the same time this is possible by changing the filter:

!!! example
    ```python
	TEST_SESSION [10]: for node in get_session_node(current_session.name).iterator.walk(filter=['scan_group','scan'],wait=False):
		      ...:     print(node.db_name,node.info["scan_nb"])
	test_session:tmp:scans:53_loopscan 53
	test_session:tmp:scans:54_loopscan 54
	test_session:tmp:scans:55_sequence_of_scans 55
	test_session:tmp:scans:56_loopscan 56
	test_session:tmp:scans:57_loopscan 57
    ```

For online data analysis it is possible to be notified when a new scan is added to a sequence:

!!! example
    ```python
	TEST_SESSION [28]: for (event,node,data) in seq.node.iterator.walk_events(filter='node_ref_channel'):
		      ...:     print(event, node.db_name)
		      ...:     if event.name == "NEW_DATA":
		      ...:         print("\t" , node.get(0,-1))
	event.NEW_NODE test_session:tmp:scans:310_sequence_of_scans:GroupingMaster:scans
	event.NEW_DATA test_session:tmp:scans:310_sequence_of_scans:GroupingMaster:scans
		 [<bliss.data.scan.Scan object at 0x7f527a7b2710>, <bliss.data.scan.Scan object at 0x7f527a7b22d0>]

    ```


