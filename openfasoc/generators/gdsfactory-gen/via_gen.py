from gdsfactory.cell import cell
from gdsfactory.component import Component
from gdsfactory.components.rectangle import rectangle
from pydantic import validate_arguments
from collections import OrderedDict
from PDK.mappedpdk import MappedPDK
from math import ceil, floor


@validate_arguments
def __error_check_order_layers(
    pdk: MappedPDK, glayer1: str, glayer2: str
) -> tuple[int, int]:
    """correctly order layers (level1 should be lower than level2)"""
    pdk.activate()
    # check that the generic layers specfied can be routed between
    if not all([pdk.is_routable_glayer(met) for met in [glayer1, glayer2]]):
        raise ValueError("via_stack: specify between two routable layers")
    level1 = int(glayer1[-1]) if "met" in glayer1 else 0
    level2 = int(glayer2[-1]) if "met" in glayer2 else 0
    if level1 > level2:
        level1, level2 = level2, level1
    return level1, level2


@cell
def via_stack(pdk: MappedPDK, glayer1: str, glayer2: str) -> Component:
    """produces a single via stack between two metal layers
    does not produce via arrays
    args:
    pdk: MappedPDK is the pdk to use
    glayer1: str is the glayer to start on
    glayer2: str is the glayer to end on
    ****NOTE it does not matter what order you pass layers
    ****NOTE will not lay poly or active but will lay metals
    """
    level1, level2 = __error_check_order_layers(pdk, glayer1, glayer2)
    viastack = Component()
    # if same level return empty component
    if level1 == level2:
        return viastack
    # lay mcon if first layer is active or poly
    if not level1:
        pdk.has_required_glayers(["mcon", "met1"])
        mcondim = pdk.get_grule("mcon")["width"]
        viastack << rectangle(
            size=(mcondim, mcondim), layer=pdk.get_glayer("mcon"), centered=True
        )
        metdim = max(
            2 * pdk.get_grule("met1", "mcon")["min_enclosure"] + mcondim,
            pdk.get_grule("met1")["min_width"],
        )
        viastack << rectangle(
            size=(metdim, metdim), layer=pdk.get_glayer("met1"), centered=True
        )
        # add one to level1 (make it a metal) so we can use the code below
        level1 += 1
        # check if layers are now same
        if level1 == level2:
            return viastack.flatten()
    # construct metal stack if both are metals
    if level1 and level2:
        for level in range(level1, level2):
            gmetlayer = "met" + str(level)
            gnextvia = "via" + str(level)
            pdk.has_required_glayers([gmetlayer, gnextvia])
            metdim = max(
                2 * pdk.get_grule(gmetlayer, gnextvia)["min_enclosure"]
                + pdk.get_grule(gnextvia)["width"],
                pdk.get_grule(gmetlayer)["min_width"],
            )
            viastack << rectangle(
                size=(metdim, metdim), layer=pdk.get_glayer(gmetlayer), centered=True
            )
            viadim = pdk.get_grule(gnextvia)["width"]
            viastack << rectangle(
                size=(viadim, viadim), layer=pdk.get_glayer(gnextvia), centered=True
            )
        gfinalmet = "met" + str(level2)
        gprevvia = "via" + str(level)
        metdim = max(
            2 * pdk.get_grule(gfinalmet, gprevvia)["min_enclosure"]
            + pdk.get_grule(gprevvia)["width"],
            pdk.get_grule(gfinalmet)["min_width"],
        )
        viastack << rectangle(
            size=(metdim, metdim), layer=pdk.get_glayer(gfinalmet), centered=True
        )
    return viastack.flatten()


@cell
def via_array(pdk: MappedPDK, glayer1: str, glayer2: str, size=(4.0, 2.0)) -> Component:
    """Fill a region with vias. Will automatically decide num rows and columns
    args:
    pdk: MappedPDK is the pdk to use
    glayer1: str is the glayer to start on
    glayer2: str is the glayer to end on
    ****NOTE it does not matter what order you pass layers
    ****NOTE will not lay poly or active but will lay metals
    size: tuple is the (width, hieght) of the area to enclose
    ****NOTE: the size will be the dimensions of the top metal
    """
    level1, level2 = __error_check_order_layers(pdk, glayer1, glayer2)
    viaarray = Component()
    # if same level return empty component
    if level1 == level2:
        return viaarray
    # figure out min space between via stacks
    via_spacing = [] if level1 else [pdk.get_grule("mcon")["min_seperation"]]
    level1 = level1 if level1 else level1 + 1
    for level in range(level1, level2):
        met_glayer = "met" + str(level)
        via_glayer = "via" + str(level)
        via_spacing.append(pdk.get_grule(met_glayer)["min_seperation"])
        via_spacing.append(pdk.get_grule(via_glayer)["min_seperation"])
    via_spacing.append(pdk.get_grule("met" + str(level2))["min_seperation"])
    via_spacing = max(via_spacing)
    # error check size and get viaspacing_full
    viastack = via_stack(pdk, glayer1, glayer2)
    viadim = max(viastack.xmax - viastack.xmin, viastack.ymax - viastack.ymin)
    if any([viadim > dim for dim in size]):
        raise ValueError("via_array size: one or more dims too small")
    viaspacing_full = via_spacing + viadim
    # num_vias[0]=x, num_vias[1]=y
    num_vias = [(floor(dim / (viadim + via_spacing)) or 1) for dim in size]
    # num_vias = [(dim-1 if dim>1 else dim) for dim in num_vias]
    # create horizontal vias and center
    horizontal_vias = Component("temp horizontal vias")
    for vianum in range(num_vias[0]):
        spacing_multiplier = ((-1) ** vianum) * ceil(vianum / 2)
        viastack_ref = horizontal_vias << viastack
        viastack_ref.movex(spacing_multiplier * viaspacing_full)
        if (num_vias[0] % 2) == 0:  # adjust for even array size
            viastack_ref.movex(viaspacing_full / 2)
    # copy horizontal to create vertical
    for vianum in range(num_vias[1]):
        spacing_multiplier = ((-1) ** vianum) * ceil(vianum / 2)
        viarow_ref = viaarray << horizontal_vias
        viarow_ref.movey(spacing_multiplier * viaspacing_full)
        if (num_vias[1] % 2) == 0:  # adjust for even array size
            viarow_ref.movey(viaspacing_full / 2)
    # place top metal and return
    top_met_layer = pdk.get_glayer("met" + str(level2))
    viaarray << rectangle(size=size, layer=top_met_layer, centered=True)
    return viaarray.flatten()


if __name__ == "__main__":
    from PDK.gf180_mapped import gf180_mapped_pdk

    gf180_mapped_pdk.activate()
    via_array(gf180_mapped_pdk, "active_diff", "met1").show()
