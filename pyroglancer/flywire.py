#    This script is part of pyroglancer (https://github.com/SridharJagannathan/pyroglancer).
#    Copyright (C) 2020 Sridhar Jagannathan
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.

"""Module contains functions to handle neuroglancer layers for flywire tracing."""

from .utils import get_alphavalue
from .utils import get_hexcolor
import cloudvolume
import json
from nglui.statebuilder import PointMapper, LineMapper, AnnotationLayerConfig, StateBuilder, ChainedStateBuilder
from pyroglancer.layers import add_precomputed
import requests
from .skeletons import skeletons2nodepoints
from .synapses import synapses2nodepoints
from urllib.parse import parse_qs
from urllib.parse import urlparse
from .utils import get_annotationstatetype
from .utils import get_scalevalue


FLYWIRESTATE_URL = 'https://globalv1.flywire-daf.com/nglstate'
FLYWIREHOST_URL = 'https://ngl.flywire.ai'


def flywireurl2dict(flywireurl):
    """Return dict from a flywire based short or long url.

    Parameters
    ----------
    flywireurl: short or long url of the flywire instance

    Returns
    -------
    ngdict: dict containing different layers of the flywire instance
    """
    assert isinstance(flywireurl, (str, dict))

    # get the query string..
    queryurl = urlparse(flywireurl).query
    # convert query to string..
    querystring = parse_qs(queryurl, keep_blank_values=True)

    if 'json_url' in querystring:
        # Get the layers from the json file as query
        token = cloudvolume.secrets.chunkedgraph_credentials['token']
        response = requests.get(querystring['json_url'][0], headers={'Authorization': f"Bearer {token}"})
        response.raise_for_status()

        ngdict = response.json()
    else:
        ngdict = querystring

    return ngdict


def flywiredict2url(ngdict):
    """Return a flywire based short url.

    Parameters
    ----------
    ngdict: dict containing different layers of the flywire instance

    Returns
    -------
    flywireurl: short url of the flywire instance
    """
    token = cloudvolume.secrets.chunkedgraph_credentials['token']
    jsonbaseurl = FLYWIRESTATE_URL
    flywirebaseurl = FLYWIREHOST_URL
    session = requests.Session()

    requesturl = f'{jsonbaseurl}/post'
    response = session.post(requesturl, data=json.dumps(ngdict),
                            headers={'Authorization': f"Bearer {token}"})
    response.raise_for_status()

    jsonqueryurl = response.json()
    flywireurl = f'{flywirebaseurl}/?json_url={jsonqueryurl}'

    return flywireurl


def add_flywirelayer(ngdict, layer_kws):
    """Return dict from a flywire based short or long url.

    Parameters
    ----------
    ngdict: a dict containing different layers of the flywire instance
    layer_kws: a dict containing different parameters about the layer to add

    Returns
    -------
    flywireurl: url containing the updated flywire instance
    """
    layer_type = layer_kws['type']
    if layer_type == 'skeletons':
        layer_annottype = get_annotationstatetype(layer_kws)
        hexcolor = get_hexcolor(layer_kws)
        alpha = get_alphavalue(layer_kws)
        if layer_annottype == 'precomputed':
            skelseglist, layer_host = add_precomputed(layer_kws)
            if len(hexcolor) == 1:
                segmentColors = dict(map(lambda e: (e, hexcolor), skelseglist))
            else:
                segmentColors = dict(zip(skelseglist, hexcolor))

            print(segmentColors)
            skeleton_layer = {"type": "segmentation",
                              "skeletons": "precomputed://" + layer_host + "/precomputed/skeletons",
                              "skeletonRendering": {"mode2d": "lines_and_points", "mode3d": "lines"},
                              "segments": skelseglist,
                              "name": "skeleton",
                              "objectAlpha": alpha,
                              "segmentColors": segmentColors
                              }
            ngdict['layers'].append(skeleton_layer)
            flywireurl = flywiredict2url(ngdict)
            print('flywire url at:', flywireurl)
        else:
            # construct as an annotation now..
            layer_source = layer_kws['source']
            layer_scale = get_scalevalue(layer_kws)
            nodepointscollec_df = skeletons2nodepoints(layer_source, layer_scale)

            for index, neuronnodepts in nodepointscollec_df.iterrows():
                points_df = neuronnodepts['points_df']
                neuronid = neuronnodepts['id']
                lines = LineMapper(point_column_a='pointA', point_column_b='pointB')
                name = f'skel_annot_{neuronid}'
                print('color is:', hexcolor)
                anno_layer = AnnotationLayerConfig(name=name, color=hexcolor[0], mapping_rules=lines)
                sb = StateBuilder([anno_layer])
                ngdict = sb.render_state(points_df, base_state=ngdict, return_as='dict')

            flywireurl = flywiredict2url(ngdict)
            print('flywire url at:', flywireurl)

    elif layer_type == 'volumes':
        volumeidlist, layer_host = add_precomputed(layer_kws)
        layer_name = layer_kws.get('name', 'volumes')

        hexcolor = get_hexcolor(layer_kws)
        alpha = get_alphavalue(layer_kws)
        if len(hexcolor) == 1:
            segmentColors = dict(map(lambda e: (e, hexcolor), volumeidlist))
        else:
            segmentColors = dict(zip(volumeidlist, hexcolor))

        volume_layer = {"type": "segmentation",
                        "mesh": "precomputed://" + layer_host + "/precomputed/" + layer_name + "/mesh",
                        "skeletonRendering": {"mode2d": "lines_and_points", "mode3d": "lines"},
                        "segments": volumeidlist,
                        "name": "volumes",
                        "objectAlpha": alpha,
                        "segmentColors": segmentColors}
        ngdict['layers'].append(volume_layer)
        flywireurl = flywiredict2url(ngdict)
        print('flywire url at:', flywireurl)

    elif layer_type == 'synapses':
        layer_annottype = get_annotationstatetype(layer_kws)
        if layer_annottype == 'precomputed':
            layer_host = add_precomputed(layer_kws)
            presynapsepath = 'precomputed://' + layer_host + '/precomputed/presynapses'
            postsynapsepath = 'precomputed://' + layer_host + '/precomputed/postsynapses'
            presynapse_layer = {"type": "annotation",
                                "source": presynapsepath,
                                "annotationColor": "#ff0000",
                                "linkedSegmentationLayer": {"presynapses_cell": "skeleton"},
                                "filterBySegmentation": ["postsynapses_cell"],
                                "name": "presynapses"}
            postsynapse_layer = {"type": "annotation",
                                "source": postsynapsepath,
                                "annotationColor": "#0000ff",
                                "linkedSegmentationLayer": {"postsynapses_cell": "skeleton"},
                                "filterBySegmentation": ["postsynapses_cell"],
                                "name": "postsynapses"}

            ngdict['layers'].append(presynapse_layer)
            ngdict['layers'].append(postsynapse_layer)

            flywireurl = flywiredict2url(ngdict)
            print('flywire url at:', flywireurl)
        else:
            # construct as an annotation now..
            layer_source = layer_kws['source']
            layer_scale = get_scalevalue(layer_kws)
            synapsepointscollec_df = synapses2nodepoints(layer_source, layer_scale)
            hexcolor = get_hexcolor(layer_kws)
            for index, synapsenodepts in synapsepointscollec_df.iterrows():
                presyn_df = synapsenodepts['pre_syn_df']
                postsyn_df = synapsenodepts['post_syn_df']
                neuronid = synapsenodepts['id']
                presyn_mapper = PointMapper(point_column='presyn_pt')
                prename = f'presyn_annot_{neuronid}'
                presyn_annos = AnnotationLayerConfig(name=prename, color=hexcolor[0], mapping_rules=presyn_mapper)
                presyn_sb = StateBuilder(layers=[presyn_annos])

                postsyn_mapper = PointMapper(point_column='postsyn_pt')
                postname = f'postsyn_annot_{neuronid}'
                postsyn_annos = AnnotationLayerConfig(name=postname, color=hexcolor[1], mapping_rules=postsyn_mapper)
                postsyn_sb = StateBuilder(layers=[postsyn_annos])

                # Chained state builder
                chained_sb = ChainedStateBuilder([postsyn_sb, presyn_sb])
                ngdict = chained_sb.render_state([postsyn_df, presyn_df], base_state=ngdict, return_as='dict')

            flywireurl = flywiredict2url(ngdict)
            print('flywire url at:', flywireurl)

    elif layer_type == 'points':
        layer_host, layer_name = add_precomputed(layer_kws)
        pointpath = 'precomputed://' + layer_host + '/precomputed/' + layer_name
        point_layer = {"type": "annotation",
                       "source": pointpath,
                       "annotationColor": "#ff0000",
                       "name": layer_name}
        ngdict['layers'].append(point_layer)
        flywireurl = flywiredict2url(ngdict)
        print('flywire url at:', flywireurl)

    else:
        flywireurl = None

    return flywireurl
