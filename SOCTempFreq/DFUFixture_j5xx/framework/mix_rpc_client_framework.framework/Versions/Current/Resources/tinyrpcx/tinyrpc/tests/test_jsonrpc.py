#!/usr/bin/env python
# -*- coding: utf-8 -*-

import ujson as json

import pytest

from tinyrpc import MethodNotFoundError
from tinyrpc import InvalidRequestError
from tinyrpc import ServerError
from tinyrpc import RPCError
from tinyrpc import RPCResponse
from tinyrpc import InvalidReplyError
from tinyrpc.protocols.jsonrpc import JSONRPCParseError
from tinyrpc.protocols.jsonrpc import JSONRPCInvalidRequestError
from tinyrpc.protocols.jsonrpc import JSONRPCMethodNotFoundError
from tinyrpc.protocols.jsonrpc import JSONRPCInvalidParamsError
from tinyrpc.protocols.jsonrpc import JSONRPCInternalError
from tinyrpc.protocols.jsonrpc import JSONRPCSuccessResponse


def _json_equal(a, b):
    da = json.loads(a)
    db = json.loads(b)

    return da == db


@pytest.fixture
def prot():
    from tinyrpc.protocols.jsonrpc import JSONRPCProtocol

    return JSONRPCProtocol()


@pytest.mark.parametrize(('data', 'attrs'), [
    # examples from the spec, parsing only
    ("""{"jsonrpc": "2.0", "method": "subtract",
       "args": [42, 23], "id": 1}""",
     {'method': 'subtract', 'args': [42, 23], 'unique_id': 1}),

    ("""{"jsonrpc": "2.0", "method": "subtract", "args":
        [23, 42], "id": 2}""",
     {'method': 'subtract', 'args': [23, 42], 'unique_id': 2}),

    ("""{"jsonrpc": "2.0", "method": "subtract", "kwargs":
        {"subtrahend": 23, "minuend": 42}, "id": 3}""",
     {'method': 'subtract', 'kwargs': {'subtrahend': 23, 'minuend': 42},
      'unique_id': 3}),

    ("""{"jsonrpc": "2.0", "method": "subtract", "kwargs": {"minuend": 42,
        "subtrahend": 23}, "id": 4}""",
     {'method': 'subtract', 'kwargs': {'minuend': 42, 'subtrahend': 23},
      'unique_id': 4},),

    ("""{"jsonrpc": "2.0", "method": "update", "args": [1,2,3,4,5]}""",
     {'method': 'update', 'args': [1, 2, 3, 4, 5]}),

    ("""{"jsonrpc": "2.0", "method": "foobar"}""",
     {'method': 'foobar'}), ])
def test_parsing_good_request_samples(prot, data, attrs):
    req = prot.parse_request(data)

    for k, v in attrs.iteritems():
        assert getattr(req, k) == v


@pytest.mark.parametrize('invalid_json', [
    '{"jsonrpc": "2.0", "method": "foobar, "params": "bar", "baz]',
    'garbage', ])
def test_parsing_invalid_json(prot, invalid_json):
    with pytest.raises(JSONRPCParseError):
        prot.parse_request(invalid_json)


def test_parsing_invalid_arguments(prot):
    with pytest.raises(JSONRPCInvalidRequestError):
        prot.parse_request(
            """{"jsonrpc": "2.0", "method": "update", "params": 9}"""
        )


@pytest.mark.parametrize(('data', 'id', 'result'), [
    ("""{"jsonrpc": "2.0", "result": 19, "id": 1}""", 1, 19,),
    ("""{"jsonrpc": "2.0", "result": -19, "id": 2}""", 2, -19,),
    ("""{"jsonrpc": "2.0", "result": 19, "id": 3}""", 3, 19,),
    ("""{"jsonrpc": "2.0", "result": 19, "id": 4}""", 4, 19,), ])
def test_good_reply_samples(prot, data, id, result):
    reply = prot.parse_reply(data)

    assert reply.unique_id == id
    assert reply.result == result


@pytest.mark.parametrize(('exc', 'code', 'message'), [
    (JSONRPCParseError, -32700, 'Parse error'),
    (JSONRPCInvalidRequestError, -32600, 'Invalid Request'),
    (JSONRPCMethodNotFoundError, -32601, 'Method not found'),
    (JSONRPCInvalidParamsError, -32602, 'Invalid params'),
    (JSONRPCInternalError, -32603, 'Internal error'),

    # generic errors
    # (InvalidRequestError, -32600, 'Invalid Request'),
    # (MethodNotFoundError, -32601, 'Method not found'),
    # (ServerError, -32603, 'Internal error'),
])
def test_proper_construction_of_error_codes(prot, exc, code, message):
    request = prot.parse_request(
        """{"jsonrpc": "2.0", "method": "sum", "args": [1,2,4],
           "id": "1"}"""
    )
    reply = exc().error_respond().serialize()

    err = json.loads(reply)

    assert err['error']['code'] == code
    assert err['error']['message'] == '[RPCError] ' + message


def test_notification_yields_None_response(prot):
    data = """{"jsonrpc": "2.0", "method": "update", "args": [1,2,3,4,5]}"""

    req = prot.parse_request(data)

    # updates should never cause retries
    assert req.respond(True) is None


def test_batch_empty_array(prot):
    with pytest.raises(JSONRPCInvalidRequestError):
        prot.parse_request("""[]""")


def test_batch_invalid_array(prot):
    assert isinstance(prot.parse_request("""[1]""")[0],
                      JSONRPCInvalidRequestError)


def test_batch_invalid_batch(prot):
    for r in prot.parse_request("""[1, 2, 3]"""):
        assert isinstance(r, JSONRPCInvalidRequestError)


def test_batch_good_examples(prot):
    data = """
    [
        {"jsonrpc": "2.0", "method": "sum", "args": [1,2,4], "id": "1"},
        {"jsonrpc": "2.0", "method": "notify_hello", "args": [7]},
        {"jsonrpc": "2.0", "method": "subtract", "args": [42,23], "id": "2"},
        {"foo": "boo"},
        {"jsonrpc": "2.0", "method": "foo.get", "kwargs": {"name": "myself"}, "id": "5"},
        {"jsonrpc": "2.0", "method": "get_data", "id": "9"}
    ]
    """

    results = prot.parse_request(data)

    assert isinstance(results, list)
    assert results[0].method == 'sum'
    assert results[0].args == [1, 2, 4]
    assert results[0].unique_id == "1"

    assert results[1].method == 'notify_hello'
    assert results[1].args == [7]
    assert results[1].unique_id is None

    assert results[2].method == 'subtract'
    assert results[2].args == [42, 23]
    assert results[2].unique_id == "2"

    assert isinstance(results[3], JSONRPCInvalidRequestError)

    assert results[4].method == 'foo.get'
    assert results[4].kwargs == {'name': 'myself'}
    assert results[4].unique_id == "5"

    assert results[5].method == 'get_data'
    assert results[5].args == []
    assert results[5].kwargs == {}
    assert results[5].unique_id == "9"


def test_unique_ids(prot):
    req1 = prot.create_request('foo', [1, 2])
    req2 = prot.create_request('foo', [1, 2])

    assert req1.unique_id != req2.unique_id


def test_out_of_order(prot):
    req = prot.create_request('foo', ['a', 'b'], None)
    rep = req.respond(1)

    assert req.unique_id == rep.unique_id


def test_request_generation(prot):
    jdata = json.loads(prot.create_request('subtract', 42, 23).serialize())

    assert jdata['method'] == 'subtract'
    assert jdata['args'] == [42, 23]
    assert jdata['id'] is not None
    assert jdata['jsonrpc'] == '2.0'


def test_jsonrpc_spec_v2_example1(prot):
    # reset id counter
    prot._id_counter = 0

    request = prot.create_request('subtract', 42, 23)
    id = request.unique_id

    assert _json_equal(
        """{"jsonrpc": "2.0", "method": "subtract", "args": [42, 23], "id":
        """ + "\"" + id + "\"}",
        request.serialize()
    )

    reply = request.respond(19)

    assert _json_equal(
        """{"jsonrpc": "2.0", "result": 19, "id": """ + "\"" + id + "\"}",
        reply.serialize()
    )

    request = prot.create_request('subtract', 23, 42)
    id = request.unique_id
    assert _json_equal(
        """{"jsonrpc": "2.0", "method": "subtract", "args": [23, 42], "id": """ + "\"" + id + "\"}",
        request.serialize()
    )

    reply = request.respond(-19)

    assert _json_equal(
        """{"jsonrpc": "2.0", "result": -19, "id": """ + "\"" + id + "\"}",
        reply.serialize())

def test_jsonrpc_spec_v2_example2(prot):
    # reset id counter
    prot._id_counter = 2

    request = prot.create_request('subtract',
                                  **{'subtrahend': 23, 'minuend': 42})
    id = request.unique_id
    assert _json_equal(
        """{"jsonrpc": "2.0", "method": "subtract", "kwargs":
           {"subtrahend": 23, "minuend": 42}, "id": """ + "\"" + id + "\"}",
        request.serialize()
    )

    reply = request.respond(19)
    id = request.unique_id
    assert _json_equal(
        """{"jsonrpc": "2.0", "result": 19, "id": """ + "\"" + id + "\"}",
        reply.serialize())
    request = prot.create_request('subtract',
                                  **{'subtrahend': 23, 'minuend': 42})

    id = request.unique_id
    assert _json_equal(
        """{"jsonrpc": "2.0", "method": "subtract", "kwargs": {"minuend": 42, "subtrahend": 23}, "id": """ + "\"" + id + "\"}", request.serialize())

    reply = request.respond(-19)

    assert _json_equal(
        """{"jsonrpc": "2.0", "result": -19, "id": """ + "\"" + id + "\"}",
        reply.serialize())


def test_jsonrpc_spec_v2_example3(prot):
    request = prot.create_request('update', 1, 2, 3, 4, 5)
    id = request.unique_id
    assert _json_equal("""{"jsonrpc": "2.0", "method": "update", "args": [1,2,3,4,5], "id": """ + "\"" + id + "\"}", request.serialize())

    request = prot.create_request('foobar')
    id = request.unique_id
    assert _json_equal("""{"jsonrpc": "2.0", "method": "foobar", "id": """ + "\"" + id + "\"}", request.serialize())


def test_jsonrpc_spec_v2_example4(prot):
    request = prot.create_request('foobar')
    request.unique_id = str(1)

    assert _json_equal(
        """{"jsonrpc": "2.0", "method": "foobar", "id": "1"}""",
        request.serialize())

    response = request.error_respond(JSONRPCMethodNotFoundError())

    assert _json_equal(
        """{"jsonrpc": "2.0", "error": {"code": -32601, "message":
           "[RPCError] Method not found"}, "id": "1"}""", response.serialize())


def test_jsonrpc_spec_v2_example5(prot):
    try:
        prot.parse_request(
            """{"jsonrpc": "2.0", "method": "foobar, "args":
            "bar", "baz]""")
        assert False  # parsing must fail
    except JSONRPCParseError as error:
        e = error

    response = e.error_respond()

    assert _json_equal(
        """{"jsonrpc": "2.0", "error": {"code": -32700, "message":
        "[RPCError] Parse error"}, "id": null}""", response.serialize())


def test_jsonrpc_spec_v2_example6(prot):
    try:
        prot.parse_request("""{"jsonrpc": "2.0", "method": 1, "args": "bar"}""")
        assert False  # parsing must fail
    except JSONRPCInvalidRequestError as error:
        e = error

    response = e.error_respond()

    assert _json_equal(
        """{"jsonrpc": "2.0", "error": {"code": -32600, "message":
        "[RPCError] Invalid Request"}, "id": null}""", response.serialize())


def test_jsonrpc_spec_v2_example7(prot):
    try:
        prot.parse_request("""[
            {"jsonrpc": "2.0", "method": "sum", "args": [1,2,4], "id": "1"},
            {"jsonrpc": "2.0", "method" ]""")
        assert False
    except JSONRPCParseError as error:
        e = error

    response = e.error_respond()

    print response.serialize()
    assert _json_equal(
        """{"jsonrpc": "2.0", "error": {"code": -32700, "message":
           "[RPCError] Parse error"}, "id": null}""", response.serialize())


def test_jsonrpc_spec_v2_example8(prot):
    try:
        prot.parse_request("""[]""")
        assert False
    except JSONRPCInvalidRequestError as error:
        e = error

    response = e.error_respond()

    assert _json_equal("""{"jsonrpc": "2.0", "error": {"code": -32600,
    "message": "[RPCError] Invalid Request"}, "id": null}""", response.serialize())


def test_jsonrpc_spec_v2_example9(prot):
    requests = prot.parse_request("""[1]""")

    assert isinstance(requests[0], JSONRPCInvalidRequestError)

    responses = requests.create_batch_response()
    responses.append(requests[0].error_respond())

    assert _json_equal("""[ {"jsonrpc": "2.0", "error": {"code": -32600,
                       "message": "[RPCError] Invalid Request"}, "id": null} ]""",
                       responses.serialize())


def test_jsonrpc_spec_v2_example10(prot):
    requests = prot.parse_request("""[1, 2, 3]""")

    assert isinstance(requests[0], JSONRPCInvalidRequestError)
    assert isinstance(requests[1], JSONRPCInvalidRequestError)
    assert isinstance(requests[2], JSONRPCInvalidRequestError)

    responses = requests.create_batch_response()
    responses.append(requests[0].error_respond())
    responses.append(requests[1].error_respond())
    responses.append(requests[2].error_respond())

    assert _json_equal("""[
  {"jsonrpc": "2.0", "error": {"code": -32600, "message": "[RPCError] Invalid Request"}, "id": null},
  {"jsonrpc": "2.0", "error": {"code": -32600, "message": "[RPCError] Invalid Request"}, "id": null},
  {"jsonrpc": "2.0", "error": {"code": -32600, "message": "[RPCError] Invalid Request"}, "id": null}
]""", responses.serialize())


def test_jsonrpc_spec_v2_example11(prot):
    requests = prot.parse_request("""[
        {"jsonrpc": "2.0", "method": "sum", "args": [1,2,4], "id": "1"},
        {"jsonrpc": "2.0", "method": "notify_hello", "args": [7]},
        {"jsonrpc": "2.0", "method": "subtract", "args": [42,23], "id": "2"},
        {"foo": "boo"},
        {"jsonrpc": "2.0", "method": "foo.get", "kwargs": {"name": "myself"}, "id": "5"},
        {"jsonrpc": "2.0", "method": "get_data", "id": "9"}
    ]""")

    assert isinstance(requests[3], JSONRPCInvalidRequestError)

    responses = requests.create_batch_response()
    responses.append(requests[0].respond(7))
    responses.append(requests[2].respond(19))
    responses.append(requests[3].error_respond())
    responses.append(requests[4].error_respond(JSONRPCMethodNotFoundError()))
    responses.append(requests[5].respond(['hello', 5]))

    assert _json_equal("""[
        {"jsonrpc": "2.0", "result": 7, "id": "1"},
        {"jsonrpc": "2.0", "result": 19, "id": "2"},
        {"jsonrpc": "2.0", "error": {"code": -32600, "message": "[RPCError] Invalid Request"}, "id": null},
        {"jsonrpc": "2.0", "error": {"code": -32601, "message": "[RPCError] Method not found"}, "id": "5"},
        {"jsonrpc": "2.0", "result": ["hello", 5], "id": "9"}
    ]""", responses.serialize())


def test_jsonrpc_spec_v2_example12(prot):
    reqs = []
    reqs.append(prot.create_request('notify_sum', [1, 2, 4], one_way=True))
    reqs.append(prot.create_request('notify_hello', [7], one_way=True))

    request = prot.create_batch_request(reqs)

    assert request.create_batch_response() is None


def test_can_get_custom_error_messages_out(prot):
    request = prot.create_request('foo')

    custom_msg = 'join the army, they said. see the world, they said.'

    e = Exception(custom_msg)

    response = request.error_respond(e)

    data = json.loads(response.serialize())

    assert data['error']['message'] == '[RPCError] ' + custom_msg


def test_accepts_empty_but_not_none_args_kwargs(prot):
    request = prot.create_request('foo', args=[], kwargs={})


def test_missing_jsonrpc_version_on_request(prot):
    with pytest.raises(JSONRPCInvalidRequestError):
        prot.parse_request('{"method": "sum", "params": [1,2,4], "id": "1"}')


def test_missing_jsonrpc_version_on_reply(prot):
    with pytest.raises(InvalidReplyError):
        prot.parse_reply('{"result": 7, "id":test_pass_error_data_with_standard_exception "1"}')

def test_pass_error_data_with_standard_exception(prot):
    request = prot.create_request('foo')

    custom_msg = 'join the army, they said. see the world, they said.'
    data = {'pi': 3.14, 'lst': ['a', 'b', 'c']}

    e = Exception(custom_msg)
    response = request.error_respond(e)

    decoded = json.loads(response.serialize())
    assert decoded['error']['code'] == -32000
    assert decoded['error']['message'] == '[RPCError] ' + custom_msg

def test_pass_error_data_with_custom_exception(prot):
    request = prot.create_request('foo')

    data = {'pi': 3.14, 'lst': ['a', 'b', 'c']}

    e = JSONRPCParseError()

    response = request.error_respond(e)

    decoded = json.loads(response.serialize())
    assert decoded['error']['code'] == -32700
    assert decoded['error']['message'] == '[RPCError] ' + JSONRPCParseError.message

def test_error_request(prot):

    reply_dict = {'jsonrpc': "3.0", 'id': 0, 'method': 'test', 'result': '--PASS--'}
    with pytest.raises(Exception) as e:
        prot.parse_reply(json.dumps(reply_dict))
    assert e.typename == 'InvalidReplyError' and 'Key not allowed: method' in str(e)
    reply_dict.pop('method')
    with pytest.raises(Exception) as e:
        prot.parse_reply(json.dumps(reply_dict))
    assert e.typename == 'InvalidReplyError' and 'Wrong JSONRPC version' in str(e)
    reply_dict['jsonrpc'] = "2.0"
    reply_dict.pop('result')
    with pytest.raises(Exception) as e:
        prot.parse_reply(json.dumps(reply_dict))
    assert e.typename == 'InvalidReplyError' and 'Reply must contain exactly one of result and error.' in str(e)
    reply_dict.pop('id')
    with pytest.raises(Exception) as e:
        prot.parse_reply(json.dumps(reply_dict))
    assert e.typename == 'InvalidReplyError' and 'Missing id in response' in str(e)
    reply_dict.pop('jsonrpc')
    with pytest.raises(Exception) as e:
        prot.parse_reply(json.dumps(reply_dict))
    assert e.typename == 'InvalidReplyError' and 'Missing jsonrpc (version) in response.' in str(e)
