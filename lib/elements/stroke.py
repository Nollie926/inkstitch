import sys
import shapely.geometry

from .element import param, EmbroideryElement, Patch
from ..i18n import _
from ..utils import cache, Point
from ..stitches import running_stitch
from ..svg import parse_length_with_units

warned_about_legacy_running_stitch = False


class Stroke(EmbroideryElement):
    element_name = "Stroke"

    @property
    @param('satin_column', _('Satin stitch along paths'), type='toggle', inverse=True)
    def satin_column(self):
        return self.get_boolean_param("satin_column")

    @property
    def color(self):
        return self.get_style("stroke")

    @property
    def dashed(self):
        return self.get_style("stroke-dasharray") is not None

    @property
    @param('running_stitch_length_mm', _('Running stitch length'), unit='mm', type='float', default=1.5)
    def running_stitch_length(self):
        return max(self.get_float_param("running_stitch_length_mm", 1.5), 0.01)

    @property
    @param('zigzag_spacing_mm', _('Zig-zag spacing (peak-to-peak)'), unit='mm', type='float', default=0.4)
    @cache
    def zigzag_spacing(self):
        return max(self.get_float_param("zigzag_spacing_mm", 0.4), 0.01)

    @property
    @param('repeats', _('Repeats'), type='int', default="1")
    def repeats(self):
        return self.get_int_param("repeats", 1)

    @property
    def paths(self):
        path = self.parse_path()

        if self.manual_stitch_mode:
            return [self.strip_control_points(subpath) for subpath in path]
        else:
            return self.flatten(path)

    @property
    @cache
    def shape(self):
        line_strings = [shapely.geometry.LineString(path) for path in self.paths]
        return shapely.geometry.MultiLineString(line_strings)

    @property
    @param('manual_stitch', _('Manual stitch placement'), tooltip=_("Stitch every node in the path.  Stitch length and zig-zag spacing are ignored."), type='boolean', default=False)
    def manual_stitch_mode(self):
        return self.get_boolean_param('manual_stitch')

    def is_running_stitch(self):
        # using stroke width <= 0.5 pixels to indicate running stitch is deprecated in favor of dashed lines

        stroke_width, units = parse_length_with_units(self.get_style("stroke-width", "1"))

        if self.dashed:
            return True
        elif stroke_width <= 0.5 and self.get_float_param('running_stitch_length_mm', None) is not None:
            # if they use a stroke width less than 0.5 AND they specifically set a running stitch
            # length, then assume they intend to use the deprecated <= 0.5 method to set running
            # stitch.
            #
            # Note that we use self.get_style("stroke_width") _not_ self.stroke_width above.  We
            # explicitly want the stroke width in "user units" ("document units") -- that is, what
            # the user sees in inkscape's stroke settings.
            #
            # Also note that we don't use self.running_stitch_length_mm above.  This is because we
            # want to see if they set a running stitch length at all, and the property will apply
            # a default value.
            #
            # Thsi is so tricky, and and intricate that's a major reason that we deprecated the
            # 0.5 units rule.

            # Warn them the first time.
            global warned_about_legacy_running_stitch
            if not warned_about_legacy_running_stitch:
                warned_about_legacy_running_stitch = True
                print >> sys.stderr, _("Legacy running stitch setting detected!\n\nIt looks like you're using a stroke " + \
                    "smaller than 0.5 units to indicate a running stitch, which is deprecated.  Instead, please set " + \
                    "your stroke to be dashed to indicate running stitch.  Any kind of dash will work.")

            # still allow the deprecated setting to work in order to support old files
            return True
        else:
            return False

    def simple_satin(self, path, zigzag_spacing, stroke_width):
        "zig-zag along the path at the specified spacing and wdith"

        # `self.zigzag_spacing` is the length for a zig and a zag
        # together (a V shape).  Start with running stitch at half
        # that length:
        patch = self.running_stitch(path, zigzag_spacing / 2.0)

        # Now move the points left and right.  Consider each pair
        # of points in turn, and move perpendicular to them,
        # alternating left and right.

        offset = stroke_width / 2.0

        for i in xrange(len(patch) - 1):
            start = patch.stitches[i]
            end = patch.stitches[i + 1]
            segment_direction = (end - start).unit()
            zigzag_direction = segment_direction.rotate_left()

            if i % 2 == 1:
                zigzag_direction *= -1

            patch.stitches[i] += zigzag_direction * offset

        return patch

    def running_stitch(self, path, stitch_length):
        repeated_path = []

        # go back and forth along the path as specified by self.repeats
        for i in xrange(self.repeats):
            if i % 2 == 1:
                # reverse every other pass
                this_path = path[::-1]
            else:
                this_path = path[:]

            repeated_path.extend(this_path)

        stitches = running_stitch(repeated_path, stitch_length)

        return Patch(self.color, stitches)


    def to_patches(self, last_patch):
        patches = []

        for path in self.paths:
            path = [Point(x, y) for x, y in path]
            if self.manual_stitch_mode:
                patch = Patch(color=self.color, stitches=path, stitch_as_is=True)
            elif self.is_running_stitch():
                patch = self.running_stitch(path, self.running_stitch_length)
            else:
                patch = self.simple_satin(path, self.zigzag_spacing, self.stroke_width)

            if patch:
                patches.append(patch)

        return patches
