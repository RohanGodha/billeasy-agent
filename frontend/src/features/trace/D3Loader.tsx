import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { themeColor } from '@/lib/theme';

/**
 * A compact D3 "thinking" loader: orbiting nodes with a pulsing core, drawn on
 * an SVG and animated with d3 timers. Cheap, smooth, GPU-friendly.
 */
export function D3Loader({ size = 28, label }: { size?: number; label?: string }) {
  const ref = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    const svg = d3.select(ref.current);
    svg.selectAll('*').remove();
    const c = size / 2;
    const r = size * 0.34;
    const n = 6;

    const g = svg.append('g').attr('transform', `translate(${c},${c})`);

    const accent = themeColor('accent', '#3b82f6');
    const accentGlow = themeColor('accent-glow', '#60a5fa');

    // core
    const core = g.append('circle').attr('r', size * 0.1).attr('fill', accent);

    const dots = g
      .selectAll('circle.dot')
      .data(d3.range(n))
      .enter()
      .append('circle')
      .attr('class', 'dot')
      .attr('r', size * 0.07)
      .attr('fill', accentGlow);

    const timer = d3.timer((elapsed) => {
      const t = elapsed / 1000;
      dots
        .attr('cx', (d) => Math.cos((d / n) * 2 * Math.PI + t * 2) * r)
        .attr('cy', (d) => Math.sin((d / n) * 2 * Math.PI + t * 2) * r)
        .attr('opacity', (d) => 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(t * 3 - d)));
      core.attr('r', size * 0.1 * (1 + 0.18 * Math.sin(t * 4)));
    });

    return () => timer.stop();
  }, [size]);

  return (
    <span className="inline-flex items-center gap-2">
      <svg ref={ref} width={size} height={size} />
      {label && <span className="text-xs text-text-muted">{label}</span>}
    </span>
  );
}
