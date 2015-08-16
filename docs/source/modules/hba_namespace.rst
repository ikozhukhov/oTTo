HBA Namespace Definition
------------------------
Google JSON style http://google-styleguide.googlecode.com/svn/trunk/jsoncstyleguide.xml

JSON definitons are in Orderly format: http://orderly-json.org/


/sysinfo
========
General information about the system::

    object {
        string type [ "HBA" ];
        string version;
        string hostname?;
        string hostuuid?;	// Due to hardware vendors not behaving, you cannot assume this to be unique
        string ostype? [ "Linux", "ESXi", "Windows", "Solaris"];
        string osversion?;
        string osarch? [ "32bit", "64bit"];
     }*;

/sysdiag
========
Combined HBA Debug variables::

    object {
        integer srcnt;
        integer sgcnt;
        integer sgbufcnt;
        integer arcnt;
        integer srallocfail;
        integer sgallocfail;
        integer sgbufallocfail;
        integer arallocfail;
        integer cectx;			// CEC frames transmitted
        integer cecrx;			// CEC frames received
        integer cecdr;			// CEC frames dropped
        integer shortcap;		// CAP frame too short
        integer badcap;			// CAP frame not terminated
        integer badcappair;		// CAP frame pair not read correctly
        integer iosubmit;
        integer iorequest;
        integer ioqueue;
        integer iosend;
        integer ioretire;
        integer cmdtrace;
        integer srdebug;
        integer rqsize;
        integer tdeadsecs;
        integer qdepth;
        string version;
    }*;

/net/el/diag
============
Management Network Protocol Diagnostic information::

    object {
        integer InMsgs;
        integer OutMsgs;
        integer HlenErrs;		// Header length error
        integer LenErrs;		// Short Packet
        integer Retrans;
        integer DropNoMatch;
        integer DropReject;
        integer DropNoSync;
        integer DropNoAvail;
        integer DropNoWait;
        integer DropQpass;
        integer DropSeq;
        integer ArpIn;
        integer ArpOut;
        array [
            string eldest;				// ARP tba, el address
            integer nroutes;			// count of routes
            array [ integer ] routes;	// current routes for round robin communication - subset of targs indices
            array [
                integer index;			// route index
                integer rtept;			// Current route port
                string ea;				// Destination ethernet address
                integer link;
                integer mtu;
                integer ports;
                integer recent;
            ] targs;
        ] elarps;
        array [
            integer tab;				// EL line directory
            string state;				// Connection state
            string ECB;					// Local and Remote addresses/ports
            integer id0;				// Local starting sequence number
            integer rid0;				// Remote starting sequence number
            integer rcvd;				// Last in-sequence msg received from remote
            integer delayedack;			// Counter of contiguous data frames we've delay acked
            integer flags;
            integer resends;
            integer rxidle;				// Last time remote sent to us
            integer txidle;				// Last time we sent to remote
            integer crto;				// Timeout for oq[0], base rto<<retrie
            integer rto;				// Base resend timeout
            integer sa;					// Scaled average RTT
            integer sv;					// Scaled variance of RTT
            integer rttseq;				// Sequence of current rtt timing
            integer opens;				// number of times this ecb is used
            integer rqlen;				// Number of input/read queue packets
            integer outqlen;			// Number of output/send queue packets
            integer deathtime;			// Timeout in ms for connection timeout
            integer cwnd;				// Current window
            integer sswnd;				// Slow start window
            integer nsswnd;				// Current slow start success counter
            integer out;				// Current outstanding
            integer unacked;			// Sequence num of 1st unack'd msg on local side
            integer next;				// Next ID msg to be sent from local side
            string creason;				// Details why connection was closed
            array [
                    integer wnd;		// ecb data window index
                    string saddr;		// EL addr of source
                    integer sport;		// El port of source
                    string daddr;		// EL addr of destination
                    integer dport;		// EL port of desitnation
                    string type;		// EL message type
                    integer id;			// Seq id of message
                    integer ack;
                    integer len;		// Length of data (not header)
            ] wnds?;
        ] ecbs;
    }*;


/net/ports/portdiag
===================
Network Interface Ports::

    object {
        array [
            integer index;		// Port index
            string name;		// HBA model name
            string{12,12} ea;	// HBA ethernet address
            integer currentlink;
            integer maxlink;
        ] ports;
    }*;


/net/ports/ifstatdiag
=====================
Network Interface Port Stats::

    object {
        array [
            integer port;
            string model;
            string hardware?;	// i82598 only, either "i82598" or "i82599"
            string{16,16} reg;	// 16 digit hexadecimal number
            string{8,8} seen;	// 8 digit hexadecimal number - which interrupt causes have been seen since initialization
            string{8,8} icr;	// 8 digit hexadecimal number - interrupt cause register
            string{8,8} ims;	// 8 digit hexadecimal number - mask for the interrupt causes the driver cares about
            string{8,8} im?;	// i82575 only - 8 digit hexadecimal number
            string{8,8} Rdbal?;	// i82575 only - 8 digit hexadecimal number
            string{8,8} Rdbah?;	// i82575 only - 8 digit hexadecimal number
            string{8,8} Tdbal?;	// i82575 only - 8 digit hexadecimal number
            string{8,8} Tdbah?;	// i82575 only - 8 digit hexadecimal number
            string{8,8} Rxdctl?;// i82575 only - 8 digit hexadecimal number

            // present iff values are nonzero
            integer "CRC Error"?;
            integer "Alignment Error"?;					// i82575 only
            integer "Symbol Error"?;						// i82575 only
            integer "RX Error"?;							// i82575 only
            integer "Missed Packets"?;					// i82575 only
            integer "Single Collision"?;					// i82575 only
            integer "Excessive Collisions"?;				// i82575 only
            integer "Multiple Collision"?;				// i82575 only
            integer "Late Collision"?;					// i82575 only
            integer "Collision"?;							// i82575 only
            integer "Transmit Underrun"?;					// i82575 only
            integer "Defer"?;								// i82575 only
            integer "Transmit - No CRS"?;					// i82575 only
            integer "Sequence Error"?;					// i82575 only
            integer "Carrier Extension Error"?;			// i82575 only
            integer "Receive Error Length"?;				// i82575 only
            integer "Collision"?;							// i82575 only
            integer "Illegal Byte Error"?;				// i82598 only
            integer "Error Byte"?;						// i82598 only
            integer "Missed Packets 0"?;					// i82598 only
            integer "MAC Local Fault"?;					// i82598 only
            integer "MAC Remote Fault"?;					// i82598 only
            integer "Receive Length Error"?;				// i82598 only
            integer "XON Transmitted"?;
            integer "XON Received"?;
            integer "XOFF Transmitted"?;
            integer "XOFF Received"?;
            integer "FC Received Unsupported"?;			// i82575 only
            integer "Packets Received (64 Bytes)"?;
            integer "Packets Received (65-127 Bytes)"?;
            integer "Packets Received (128-255 Bytes)"?;
            integer "Packets Received (256-511 Bytes)"?;
            integer "Packets Received (512-1023 Bytes)"?;
            integer "Packets Received (1024-mtu Bytes)"?;
            integer "Good Packets Received"?;
            integer "Broadcast Packets Received"?;
            integer "Multicast Packets Received"?;
            integer "Good Octets Received"?;				// i82575 only
            integer "Good Octets Transmitted"?;			// i82575 only
            integer "Good Packets Transmitted"?;
            integer "Receive No Buffers 0"?;				// i82598 only
            integer "Receive No Buffers"?;				// i82575 only
            integer "Receive Undersize"?;
            integer "Receive Fragment"?;
            integer "Receive Oversize"?;
            integer "Receive Jabber"?;
            integer "Management Packets Rx"?;				// i82575 only
            integer "Management Packets Drop"?;			// i82575 only
            integer "Management Packets Tx"?;				// i82575 only
            integer "Total Octets Received"?;				// i82575 only
            integer "Total Octets Transmitted"?;			// i82575 only
            integer "Total Packets Received"?;
            integer "Total Packets Transmitted"?;
            integer "Packets Transmitted (64 Bytes)"?;
            integer "Packets Transmitted (65-127 Bytes)"?;
            integer "Packets Transmitted (128-255 Bytes)"?;
            integer "Packets Transmitted (256-511 Bytes)"?;
            integer "Packets Transmitted (512-1023 Bytes)"?;
            integer "Packets Transmitted (1024-mtu Bytes)"?;
            integer "Multicast Packets Transmitted"?;
            integer "Broadcast Packets Transmitted"?;
            integer "XSUM Error"?;						// i82598 only
            integer "TCP Segmentation Context Transmitted"?;// i82575 only
            integer "TCP Segmentation Context Fail"?;		// i82575 only
            integer "Interrupt Assertion"?;				// i82575 only
            integer "Interrupt Rx Pkt Timer"?;			// i82575 only
            integer "Interrupt Rx Abs Timer"?;			// i82575 only
            integer "Interrupt Tx Pkt Timer"?;			// i82575 only
            integer "Interrupt Tx Abs Timer"?;			// i82575 only
            integer "Interrupt Tx Queue Empty"?;			// i82575 only
            integer "Interrupt Tx Desc Low"?;				// i82575 only
            integer "Interrupt Rx Min"?;					// i82575 only
            integer "Interrupt Rx Overrun"?;				// i82575 only

            integer ntd;
            integer txavail;
            integer txqueuecnt;
            integer dropped;
            integer tdh;
            integer tdt;
            integer dtdh;
            integer dtdt;
            integer nrd;
            integer rdfree;
            integer rxerr;
            integer nobufs;
            integer rdh;
            integer rdt;
            integer drdh;
            integer drdt;
            integer rintr;
            integer tintr;
            integer lintr;
            integer intr;
            integer link0?;					// i82598 only
            integer link100?;				// i82598 only
            integer link1000?;				// i82598 only
            integer link10000?;				// i82598 only
            integer link;
        ] ifstats;
    }*;

/net/ports/0-9/iolive
=====================
contains the contents of the timeslice that is actively being updated, described below

/net/ports/0-9/iocurrent
========================
contains the contents of the most recently completed time slice, described below

/net/ports/0-9/iostats
======================
The array does not include the active timeslice (iolive) and is sorted from the most recently completed timeslice to oldest::

    object {
        array [
            object {
                integer period;     // length of time in seconds of this time slice
                integer timestamp;  // time in seconds from UNIX epoch as reported by the operating system for slice start
                integer now;        // time in seconds from UNIX epoch as reported by the O.S. when read is serviced
                integer cmds;       // total number of completed AoE commands in this period
                integer bytes;      // total bytes transferred of completed AoE commands in this period
                integer svctime;    // total time in milliseconds taken for completed AoE commands in this period
            }*;
        ] slices;
    }*;

/net/ports/0-9/stats
====================
Statistics for a particular HBA port::

    object {
        integer sent;
        integer received;
        integer retransmissions;
        integer fcsent?;
        integer fcreceived?;
    }*;

/net/ports/0-9/state
====================
State information for a particular HBA port::

    object {
        string model;
        integer negspeed;
        integer capspeed;
        string{16,16} mac;
    }*;

/aoe/acbdiag
============
Combined ca - Acb structs::

    object {
        array [
            string targ;		// Traditional AoE Major.Minor format.
            integer state;		// Discovery state machine with claim/release, usually 4
            integer out;		// Current outstanding requests. These commands have not yet received a response from the AoE target.
            integer wnd;		// Absolute congestion window limit for 'out', based on "buffer count" in AoE target's config query response.
            integer cwnd;		// Current congestion window limit for 'out', dynamically adjusted based on current conditions.
            integer qcnt;		// Number of SR requests on this queue.
            integer arcnt;		// Number of AoE requests for the SRs on this queue.
            integer sent;		// Total number of requests sent to an AoE target since discovery.
            integer resent;		// Number of AoE retransmissions; increments when a response is not received within the target's calculated command timeout.
            integer unex;		// Unexpected responses; occurs when a response is received after its command has already been retransmitted.
            integer ssthresh;	// Threshold for using Van Jacboson's 'slow start' or 'congestion avoidance'.  Not currently used.
            number rttavg;		// Average round trip time (ms).
            number rttdev;		// Absolute deviation average for rttavg (ms).
        ] acbs;
    }*;

/aoe/targetdiag
===============
Combined Demystifying HBA Debug#claim, Demystifying HBA Debug#config, and Demystifying HBA Debug#targets - Target structs::

    object{
        array [
            string targ;		// Traditional AoE Major.Minor format
            integer claimed;	// 1 if LUN is claimed
            integer length;		// LUN's length in bytes
            string{0,1024} cfg;	// LUN's config string
            string{40,40} model;	// ATA model number
            string{20,20} serial;	// ATA serial number
            string{8,8} firmware;	// ATA firmware version
            integer logicalsectorsize?;
            integer physicalsectorsize?;
            integer rotationalrate?;	// Drive RPM, 0 means not reported, 1 means non-rotating, other values are RPM
            string formfactor?;			// Drive form factor/size
    array [
                object {
                    string{12,12} ea;	// Target Ethernet Address
                    integer ports;		// HBA port bitmask
                    integer active;
                };
            ] tmacs;
        ] targets;
    }*;

/aoe/shelf.slot/iolive
======================
contains the contents of the timeslice that is actively being updated, described below

/aoe/shelf.slot/iocurrent
=========================
contains the contents of the most recently completed time slice, described below

/aoe/shelf.slot/iostats
=======================
A histogram by io size of various statistics for the aoe target. The array does not include the active timeslice (iolive) and is sorted from the most recently completed timeslice to oldest::

    object {
        array [
            object {
                integer period;					// length of time in seconds of this time slice
                integer timestamp;				// time in seconds from UNIX epoch as reported by the operating system for slice start
                integer now;					// time in seconds from UNIX epoch as reported by the O.S. when read is serviced
                integer osum;					// sum of the outstanding AoE requests and µs interval products in this period
                array [
                    object {
                        string iosize;			// maximum iosize for this bin
                        object {
                            integer cmds;		// total number of completed read commands of this iosize in this period
                            integer bytes;		// total bytes transferred of completed read commands of this iosize in this period
                            integer svctime;	// total time in milliseconds taken for completed read commands of this iosize in this period
                        }* read;
                        object {
                            integer cmds;		// total number of completed write commands of this iosize in this period
                            integer bytes;		// total bytes transferred of complete write commands of this iosize this period
                            integer svctime;	// total time in milliseconds taken for complete write commands of this iosize this period
                        }* write;
                    }*;
                ] bins;
            }*;
        ] slices;
    }*;

/aoe/shelf.slot/stats
=====================
Statistics for a particular aoe target:

object {
	integer sent;
	integer resent;
	integer unex;
}*;

/aoe/shelf.slot/state
=====================
State information for an aoe target { configstring, identinfo, mac:interfacemap, congavoid }:

    object {
        boolean active;	// only active aoe targets are visible to the user, i.e. flushed targets have active=false
        boolean claimed?;
        string state ["closed", "needident", "claiming", "releasing", "open", "flushed"];
        string{0,1024} configstring?;
        string{20,20} serial?;
        string{40,40} model?;
        string{8,8} firmware?;
        integer length?;
        integer logicalsectorsize?;
        integer physicalsectorsize?;
        integer rotationalrate?;	// Drive RPM, 0 means not reported, 1 means non-rotating, other values are RPM
        string formfactor?;			// Drive form factor/size
    array [
            object {
                string{12,12} mac;
                integer ports;
            };
        ] pathmap?;
        integer out;
        integer cwnd;
        integer wnd;
        number rttavg;
        number rttdev;
     }*;

/aoe/shelf.slot/ctl
===================
    This file is empty when read
    This file supports the following command written to it::

        claim [legacy] – send a claim command to the target
        release – send a release command to the target
        clear – clears the config string on the target

/aoe/ctl
========
This file is empty when read
This file supports the following commands written to it::

    flush – removes aoe targets that are no longer visible
    discover – probe the network for AoE targets

/scsi/lundiag
=============
Information about the LUNS::

    object {
        array [
            string{0,32} name;	// SCSI runtime name
            string{20,20} serial;
            string{16,31} naa;
            string targ;		// AoE target, major.minor format
            integer length;		// Length in bytes
            integer id;
            integer lun;
            string scsiaddr;
        ] luns;
    }*;
/scsi/id/iolive
===============
contains the contents of the timeslice being actively updated, described below

/scsi/id/iocurrent
==================
contains the contents of the most recently completed time slice, described below

/scsi/id/iostats
================
A histogram by iosize of various statistics for the scsi lun. This does not include the active timeslice (iolive) and is ordered from the most recently completed timeslice to oldest::

    object {
        array [
            object {
                integer period;					// length of time in seconds of this time slice
                integer timestamp;				// time in seconds from UNIX epoch as reported by the operating system for slice start
                integer now;					// time in seconds from UNIX epoch as reported by the O.S. when read is serviced
                integer qsum;					// sum of the queue length and µs interval products in this period
                integer dsts;                   // number of distances between requests
                integer dsum;                   // sum of the distance between requests in this period
                integer dsumsq;                 // sum of the square of the distance between requests in this period
                array [

                    object {
                        string iosize;			// maximum iosize for this bin
                        object {
                            integer cmds;		// total number of completed read commands of this iosize in this period
                            integer bytes;		// total bytes transferred of completed read commands of this iosize in this period
                            integer svctime;	// total time in milliseconds taken for completed read commands of this iosize in this period
                        }* read;
                        object {
                            integer cmds;		// total number of completed write commands of this iosize in this period
                            integer bytes;		// total bytes transferred of complete write commands of this iosize this period
                            integer svctime;	// total time in milliseconds taken for complete write commands of this iosize this period
                        }* write;
                    }*;
                ] bins;
            }*;
        ] slices;
    }*;
    
dsts, dsum, and dsumsq are used to calculate the mean distance between commands and the variance by applying the Naïve algorithm. If dsum and dsumsq are -1 an overflow happened and the driver stopped incrementing dsts, so the variance calculation should not be done. Steve Schleimer said the Knuth/Welford algorithm for variance/standard deviation is better than the naïve algorithm.
Example overflow::

    SRX EXPERTMODE# sed 's/"bins.*//' /n/hostname/scsi/140:22/iolive
    {"period":15,"timestamp":1375906320,"now":1375906331,"qsum":168868273,"dsts":8573,"dsum":-1,"dsumsq":-1,
    SRX EXPERTMODE#

Example standard deviation and mean calculations::

    SRX EXPERTMODE# sed 's/"bins.*//' /n/hostname/scsi/140:22/iocurrent
    {"period":15,"timestamp":1375906365,"now":1375906385,"qsum":372565732,"dsts":14392,"dsum":1046784,"dsumsq":564985856,
    SRX EXPERTMODE#

    [root@hostname tmp]# bc
    ...
    define stddev(n, s, sq) { return sqrt((sq - ((s*s)/n))/n); }
    stddev(14392, 1046784, 564985856)
    184
    1046784/14392
    72

/scsi/id/state
==============
State information for this scsi lun { serial, naa, vendor, product, size, CTLaddr, aoedev}::

    object {
        bool active;	// only active luns are presented to the operating system
        string{20, 20} serial;
        string{16, 32} naa;
        string{8, 8} vendor?;
        string{16, 16} prodid?;
        string{4, 4} prodrev?;
        integer length;
        string	scsiaddr;
        string	aoedev;
        integer logicalsectorsize?;
        integer physicalsectorsize?;
        integer rotationalrate?;	// Drive RPM, 0 means not reported, 1 means non-rotating, other values are RPM
        string formfactor?;			// Drive form factor/size
    }* scsistate;

/scsi/id/stats
==============
Statistics for the scsi lun { commands sent, received, errored }:

     object {
        integer commands;		//Total commands sent
        array [	//integer names: (skey << 16) | (asc << 8) | ascq)
            integer 0x00000?;	//NO SENSE - no sense is available
            integer 0x20401?;	//NOT READY, IN PROCESS OF BECOMING READY – used when a command is received for a LUN that doesn't exist (yet)
            integer 0x20500?;	//NOT READY, DOES NOT RESPOND TO SELECTION – used when an AoE error is received that is unknown or has no special behavior defined
            integer 0x20800?;	//NOT READY, COMMUNICATION FAILURE – used to fail outstanding commands when an AoE target is detected to have changed serial numbers
            integer 0x20801?;	//NOT READY, COMMUNICATION TIMEOUT – used to fail commands whose AoE requests are not all fulfilled within 30s
            integer 0x30c02?;	//MEDIUM ERROR, WRITE ERROR AUTO-REALLOCATION FAIL – used to fail commands that return an ATA error for a write
            integer 0x31104?;	//MEDIUM ERROR, UNRECOVERED READ ERROR AUTO-REALLOCATE FAILED – used to fail commands that return an ATA error for a read
            integer 0x43e01?;	//HARDWARE ERROR, LOGICAL UNIT FAILURE – used to fail commands that return an AoE error 3, device unavailable
            integer 0x52000?;	//ILLEGAL REQUEST, INVALID COMMAND OP CODE – used when a command is unsupported, or when a particular variation of a command is not supported
            integer 0x52100?;	//ILLEGAL REQUEST, LBA OUT OF RANGE – used when the LBA in a request is larger than the target's length
            integer 0x52400?;	//ILLEGAL REQUEST, INVALID FIELD IN CDB – used when a supported SCSI command has parameters that are invalid or not supported
            integer 0x52500?;	//ILLEGAL REQUEST, LOGICAL UNIT NOT SUPPORTED – used to fail commands when a LUN is no longer available (no response within deadsecs)
            integer 0x62a09?;	//CAPACITY DATA HAS CHANGED
            integer 0x63f00?;	//TARGET OPERATING CONDITIONS HAVE CHANGED
            integer 0x63f0e?;	//UNIT ATTENTION, REPORTED LUNS DATA HAS CHANGED – used when an AoE target has changed information
            integer 0x72700?;	//DATA PROTECT, WRITE PROTECTED – used when an ATA write fails and the ATA write protect bit is set
            integer 0xother?;	//All other sense codes
        ] sensecnts;
    }* scsistats;

Access
------
via EL
======
Get the HBA EL address and port::

[root@hostname ~]# grep Listen /proc/ethdrv/elstats
Listen [0] 5100001004010d8e!17007 0000000000000000!0 id0 2093 rid0 0 next 2093 rcvd 0 unack 2094 delayedack 0 flags 0 resends 0 rxidle 2163411651 txidle 2163411651 crto 90 rto 90 sa 50 sv 10 rttseq 0 opens 0 rqlen 0 outqlen 0 deathtime 30000
[root@hostname ~]#

Mount from Plan 9:
==================
Assuming you have drawterm and a Plan 9 account that has connectivity to the initiator, first you would need to bind the Plan9 interface (if you have not already done so)::

    bind -a '#l4' /net
    echo 'bind /net/ether4' >> /net/el/ctl

Change 4 to the appropriate port if different – also following the # is a lower case L not a pipe. Then establish the connection to the namespace over the EL link::
    srv -n el!5100001004010d8e!17007 hostname
    mount /srv/hostname /n/hostname

Then you can cd into /n/<hostname/mountpoint> and view/traverse the namespace for that initiator. When done be sure to unmount it::
    unmount /n/hostname; rm /srv/hostname

Mount from CorOS
================
Assuming the CorOS appliance is in the same SAN as the HBA::

    VSX-2.0 and SRX-7.x example
    VSX shelf 15040> /expertmode
    Expert/Diagnostic mode enabled. Proceed with caution.

    VSX EXPERTMODE# srv -n el!5100001004010d8e!17007 hostname
    post...
    VSX EXPERTMODE# mount /srv/hostname /n/hostname
    VSX EXPERTMODE# ls /n/hostname
    /n/hostname/aoe
    /n/hostname/net
    /n/hostname/scsi
    /n/hostname/sysinfo
    VSX EXPERTMODE#

Unmount::

    VSX EXPERTMODE# unmount /n/hostname; rm /srv/hostname
    VSX EXPERTMODE#

