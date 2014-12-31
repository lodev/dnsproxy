from util import config_format, port
import os


def generate(config, dnat=True, test=True):
    bind_ip = config["bind_ip"]
    server_options = config["server_options"]
    if "base_port" in config:
        current_port = config["base_port"]
    elif not dnat:
        return

    haproxy_content = generate_global()
    haproxy_content += generate_defaults()

    if not dnat:
        http_port = 80
        https_port = 443
    else:
        http_port = current_port
        https_port = current_port + 1

    haproxy_catchall_frontend_content = generate_frontend('catchall', 'http', bind_ip, http_port, True)
    haproxy_catchall_backend_content = generate_backend('catchall', 'http', None, None, None, True)

    haproxy_catchall_frontend_ssl_content = generate_frontend('catchall', 'https', bind_ip, https_port, True)
    haproxy_catchall_backend_ssl_content = generate_backend('catchall', 'https', None, None, None, True)

    if config["stats"]["enabled"]:
        haproxy_content += generate_stats(config["stats"], bind_ip)

    for group in config["groups"].values():
        for proxy in group["proxies"]:
            if not dnat or (dnat and proxy["dnat"]):
                for protocol in proxy["protocols"]:
                    if protocol == 'http':
                        haproxy_catchall_frontend_content += generate_frontend_catchall_entry(proxy["domain"], protocol)
                        haproxy_catchall_backend_content += generate_backend_catchall_entry(proxy["domain"], protocol, port(protocol), server_options)
                    elif protocol == 'https':
                        haproxy_catchall_frontend_ssl_content += generate_frontend_catchall_entry(proxy["domain"], protocol)
                        haproxy_catchall_backend_ssl_content += generate_backend_catchall_entry(proxy["domain"], protocol, port(protocol), server_options)
    if test:
        haproxy_catchall_frontend_content += generate_frontend_catchall_entry('proxy-test.trick77.com', 'http')
        haproxy_catchall_backend_content += generate_backend_catchall_entry('proxy-test.trick77.com', 'http', '80', server_options, 'trick77.com')

    haproxy_content += haproxy_catchall_frontend_content + os.linesep
    haproxy_content += haproxy_catchall_backend_content
    haproxy_content += haproxy_catchall_frontend_ssl_content + os.linesep
    haproxy_content += haproxy_catchall_backend_ssl_content

    if dnat:
        current_port += 2
        for group in config["groups"].values():
            for proxy in group["proxies"]:
                if proxy["dnat"]:
                    for protocol in proxy["protocols"]:
                        haproxy_content += generate_frontend(proxy["alias"], protocol, bind_ip, current_port, False)
                        haproxy_content += generate_backend(proxy["alias"], protocol, proxy["domain"], port(protocol), server_options, False)
                        current_port += 1

    haproxy_content += generate_deadend('http')
    haproxy_content += generate_deadend('https')

    return haproxy_content


def generate_frontend_catchall_entry(domain, mode):
    if mode == 'http':
        return config_format('use_backend b_catchall_' + mode + ' if { hdr_dom(host) -i ' + domain + ' }')

    elif mode == 'https':
        return config_format('use_backend b_catchall_' + mode + ' if { req_ssl_sni -i ' + domain + ' }')

    return None


def generate_backend_catchall_entry(domain, mode, port, server_options, override_domain=None):
    result = None
    if mode == 'http':
        result = config_format('use-server ' + domain + ' if { hdr_dom(host) -i ' + domain + ' }')
        if override_domain is None:
            result += config_format('server ' + domain + ' ' + domain + ':' + str(port) + ' ' + server_options + os.linesep)

        else:
            result += config_format('server ' + domain + ' ' + override_domain + ':' + str(port) + ' ' + server_options + os.linesep)

    elif mode == 'https':
        result = config_format('use-server ' + domain + ' if { req_ssl_sni -i ' + domain + ' }')
        result += config_format('server ' + domain + ' ' + domain + ':' + str(port) + ' ' + server_options + os.linesep)

    return result


def generate_global():
    result = config_format('global', False)
    result += config_format('daemon')
    result += config_format('maxconn 20000')
    result += config_format('user haproxy')
    result += config_format('group haproxy')
    result += config_format('stats socket /var/run/haproxy.sock mode 0600 level admin')
    result += config_format('log /dev/log local0 debug')
    result += config_format('pidfile /var/run/haproxy.pid')
    result += config_format('spread-checks 5')
    result += os.linesep
    return result


def generate_defaults():
    result = config_format('defaults', False)
    result += config_format('maxconn 19500')
    result += config_format('log global')
    result += config_format('mode http')
    result += config_format('option httplog')
    result += config_format('option abortonclose')
    result += config_format('option http-server-close')
    result += config_format('option persist')
    result += config_format('timeout connect 20s')
    result += config_format('timeout client 120s')
    result += config_format('timeout server 120s')
    result += config_format('timeout queue 120s')
    result += config_format('timeout check 10s')
    result += config_format('retries 3')
    result += os.linesep
    return result


def generate_deadend(mode):
    result = config_format('backend b_deadend_' + mode, False)
    if mode == 'http':
        result += config_format('mode http')
        result += config_format('option httplog')
        result += config_format('option accept-invalid-http-response')
        result += config_format('option http-server-close')

    elif mode == 'https':
        result += config_format('mode tcp')
        result += config_format('option tcplog')

    result += os.linesep
    return result


def generate_stats(stats, bind_ip):
    result = config_format('listen stats', False)
    result += config_format('bind ' + bind_ip + ':' + str(stats["port"]))
    result += config_format('mode http')
    result += config_format('stats enable')
    result += config_format('stats realm Protected\\ Area')
    result += config_format('stats uri /')
    result += config_format('stats auth ' + stats["user"] + ':' + stats["password"])
    result += os.linesep
    return result


def generate_frontend(proxy_name, mode, bind_ip, current_port, is_catchall):
    result = config_format('frontend f_' + proxy_name + '_' + mode, False)
    result += config_format('bind ' + bind_ip + ':' + str(current_port))

    if mode == 'http':
        result += config_format('mode http')
        result += config_format('option httplog')
        result += config_format('capture request header Host len 50')
        result += config_format('capture request header User-Agent len 150')

    elif mode == 'https':
        result += config_format('mode tcp')
        result += config_format('option tcplog')
        if is_catchall:
            result += config_format('tcp-request inspect-delay 5s')
            result += config_format('tcp-request content accept if { req_ssl_hello_type 1 }')

    if is_catchall:
        result += config_format('default_backend b_deadend_' + mode)

    else:
        result += config_format('default_backend b_' + proxy_name + '_' + mode)

    result += os.linesep
    return result


def generate_backend(proxy_name, mode, domain, port, server_options, is_catchall):
    result = config_format('backend b_' + proxy_name + '_' + mode, False)

    if mode == 'http':
        result += config_format('mode http')
        result += config_format('option httplog')
        result += config_format('option accept-invalid-http-response')

    elif mode == 'https':
        result += config_format('mode tcp')
        result += config_format('option tcplog')

    if not is_catchall:
        result += config_format('server ' + domain + ' ' + domain + ':' + str(port) + ' ' + server_options)

    return result + os.linesep
