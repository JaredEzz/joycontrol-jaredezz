import asyncio
import logging
import socket

import dbus
import pkg_resources

from joycontrol import utils
from joycontrol.device import HidDevice
from joycontrol.report import InputReport
from joycontrol.transport import L2CAP_Transport

PROFILE_PATH = pkg_resources.resource_filename('joycontrol', 'profile/sdp_record_hid.xml')
logger = logging.getLogger(__name__)


async def _send_empty_input_reports(transport):
    report = InputReport()
    for i in range(10):
        await transport.write(report)
        await asyncio.sleep(1)


async def create_hid_server(protocol_factory, ctl_psm=17, itr_psm=19, device_id=None, reconnect_bt_addr=None,
                            capture_file=None):
    """
    :param protocol_factory: Factory function returning a ControllerProtocol instance
    :param ctl_psm: hid control channel port
    :param itr_psm: hid interrupt channel port
    :param device_id: ID of the bluetooth adapter.
                      Integer matching the digit in the hci* notation (e.g. hci0, hci1, ...) or
                      Bluetooth mac address in string notation of the adapter (e.g. "FF:FF:FF:FF:FF:FF").
                      If None, choose any device.
                      Note: Selection of adapters may currently not work if the bluez "input" plugin is enabled.
    :param reconnect_bt_addr: The Bluetooth address of the console that was previously connected. Defaults to None.
                      If None, a new hid server will be started for the initial paring.
                      Otherwise, the function assumes an initial pairing with the console was already done
                      and reconnects to the provided Bluetooth address.
    :param capture_file: opened file to log incoming and outgoing messages
    :returns transport for input reports and protocol which handles incoming output reports
    """
    protocol = protocol_factory()

    if reconnect_bt_addr is None:
        ctl_sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
        itr_sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
        ctl_sock.setblocking(False)
        itr_sock.setblocking(False)
        ctl_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        itr_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            hid = HidDevice(device_id=device_id)

            ctl_sock.bind((hid.address, ctl_psm))
            itr_sock.bind((hid.address, itr_psm))
        except OSError as err:
            logger.warning(err)
            # If the ports are already taken, this probably means that the bluez "input" plugin is enabled.
            logger.warning('Fallback: Restarting bluetooth due to incompatibilities with the bluez "input" plugin. '
                           'Disable the plugin to avoid issues. See https://github.com/mart1nro/joycontrol/issues/8.')
            # HACK: To circumvent incompatibilities with the bluetooth "input" plugin, we need to restart Bluetooth here.
            # The Switch does not connect to the sockets if we don't.
            # For more info see: https://github.com/mart1nro/joycontrol/issues/8
            logger.info('Restarting bluetooth service...')
            await utils.run_system_command('systemctl restart bluetooth.service')
            await asyncio.sleep(1)

            hid = HidDevice(device_id=device_id)

            ctl_sock.bind((socket.BDADDR_ANY, ctl_psm))
            itr_sock.bind((socket.BDADDR_ANY, itr_psm))

        ctl_sock.listen(1)
        itr_sock.listen(1)

        hid.powered(True)
        hid.pairable(True)

        logger.info('Advertising the Bluetooth SDP record...')
        try:
            HidDevice.register_sdp_record(PROFILE_PATH)
        except dbus.exceptions.DBusException as dbus_err:
            # Already registered (If multiple controllers are being emulated and this method is called consecutive times)
            logger.debug(dbus_err)

        # start advertising
        hid.discoverable()

        logger.info('Waiting for Switch to connect... Please open the "Change Grip/Order" menu.')

        loop = asyncio.get_event_loop()
        client_ctl, ctl_address = await loop.sock_accept(ctl_sock)
        logger.info(f'Accepted connection at psm {ctl_psm} from {ctl_address}')
        client_itr, itr_address = await loop.sock_accept(itr_sock)
        logger.info(f'Accepted connection at psm {itr_psm} from {itr_address}')
        assert ctl_address[0] == itr_address[0]

        # stop advertising
        hid.discoverable(False)
        hid.pairable(False)

    else:
        # Reconnection to reconnect_bt_addr
        client_ctl = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
        client_itr = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
        client_ctl.connect((reconnect_bt_addr, ctl_psm))
        client_itr.connect((reconnect_bt_addr, itr_psm))
        client_ctl.setblocking(False)
        client_itr.setblocking(False)

    # create transport for the established connection and activate the HID protocol
    transport = L2CAP_Transport(asyncio.get_event_loop(), protocol, client_itr, client_ctl, 50, capture_file=capture_file)
    protocol.connection_made(transport)

    # HACK: send some empty input reports until the Switch decides to reply
    future = asyncio.ensure_future(_send_empty_input_reports(transport))
    await protocol.wait_for_output_report()
    """
    future.cancel()
    try:
        await future
    except asyncio.CancelledError:
        pass
    """

    return protocol.transport, protocol
