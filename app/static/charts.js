function bazaarCharts(root) {
  if (!window.Chart) return;
  const node = (root || document).querySelector("#chart-data");
  if (!node) return;
  let data;
  try {
    data = JSON.parse(node.textContent);
  } catch (err) {
    return;
  }
  const ink = "#1b1612";
  const muted = "#8a8175";
  const grid = "#efe8dc";
  const marigold = "#d86a1c";
  const indigo = "#1b3c4d";
  const last = "#c4b49a";
  Chart.defaults.font.family = '"Outfit", "Segoe UI", sans-serif';
  Chart.defaults.color = muted;

  const yoy = root.querySelector("#yoy-chart");
  if (yoy && data.yoy && data.yoy.labels.length) {
    draw(() => new Chart(yoy, {
      type: "line",
      data: {
        labels: data.yoy.labels,
        datasets: [
          {
            label: data.yoy.lastYear || "Last year",
            data: data.yoy.last,
            borderColor: last,
            backgroundColor: last,
            tension: 0.25,
            pointRadius: 0,
            borderWidth: 2,
          },
          {
            label: data.yoy.thisYear || "This year",
            data: data.yoy.this,
            borderColor: marigold,
            backgroundColor: marigold,
            tension: 0.25,
            pointRadius: 0,
            borderWidth: 2.5,
          },
        ],
      },
      options: chartOptions(),
    }));
  }

  const five = root.querySelector("#five-chart");
  if (five && data.five && data.five.labels.length) {
    const annotations = {};
    (data.five.markers || []).forEach((marker, index) => {
      annotations["d" + index] = {
        type: "line",
        scaleID: "x",
        value: marker.label,
        borderColor: marigold,
        borderWidth: 1,
        borderDash: [3, 3],
        label: {
          display: true,
          content: marker.text,
          position: "start",
          backgroundColor: "rgba(216,106,28,0.9)",
          color: "#fff",
          font: { size: 10 },
        },
      };
    });
    draw(() => new Chart(five, {
      type: "line",
      data: {
        labels: data.five.labels,
        datasets: [
          {
            label: data.five.term || "Interest",
            data: data.five.values,
            borderColor: indigo,
            backgroundColor: "rgba(27,60,77,0.08)",
            fill: true,
            tension: 0.2,
            pointRadius: 0,
            borderWidth: 2,
          },
        ],
      },
      options: {
        ...chartOptions(),
        plugins: {
          ...chartOptions().plugins,
          annotation: { annotations },
        },
      },
    }));
  }

  const states = root.querySelector("#state-chart");
  if (states && data.states && data.states.labels.length) {
    draw(() => new Chart(states, {
      type: "bar",
      data: {
        labels: data.states.labels,
        datasets: [
          {
            label: "Interest",
            data: data.states.values,
            backgroundColor: data.states.served.map((on) => (on ? marigold : indigo)),
            borderRadius: 4,
          },
        ],
      },
      options: {
        indexAxis: "y",
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: grid }, ticks: { color: muted } },
          y: { grid: { display: false }, ticks: { color: ink } },
        },
      },
    }));
  }

  const bands = root.querySelector("#band-chart");
  if (bands && data.bands && data.bands.labels.length) {
    draw(() => new Chart(bands, {
      type: "bar",
      data: {
        labels: data.bands.labels,
        datasets: [
          {
            label: "Listings",
            data: data.bands.counts,
            backgroundColor: data.bands.labels.map((_, i) => {
              if (data.bands.whitespace[i]) return "#1c6b43";
              if (data.bands.target[i]) return marigold;
              return indigo;
            }),
            borderRadius: 6,
          },
        ],
      },
      options: chartOptions(),
    }));
  }
}

function draw(fn) {
  try {
    fn();
  } catch (err) {
    console.error(err);
  }
}

function chartOptions() {
  return {
    plugins: { legend: { labels: { boxWidth: 12 } } },
    scales: {
      x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 } },
      y: { beginAtZero: true, grid: { color: "#efe8dc" } },
    },
  };
}

document.addEventListener("DOMContentLoaded", () => bazaarCharts(document));
document.body.addEventListener("htmx:afterSwap", (event) => bazaarCharts(event.target));
