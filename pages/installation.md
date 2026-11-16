# Installing CART

## Prerequisites

Please ensure you have downloaded the following for your specific operating system before beginning:

- 3D Slicer version 5.8 or above (tested up to version 5.12):
  - Download the latest version [here](https://download.slicer.org/).
- A copy of CART:
  - Recommended: the [latest release](https://github.com/neuropoly/slicer-cart/releases/latest).
  - Cutting Edge: the [developer ZIP archive](https://github.com/neuropoly/slicer-cart/archive/refs/heads/main.zip)

Both should be unzipped in a place you can easily find.

## Installing CART

1. Locate your (unzipped) CART directory, then the `CART/` directory within it. This should contain a `CART.py` file
2. Start Slicer and wait for it to finish loading
3. In Slicer, go to `Edit` > `Application Settings`: 

![Screenshot showing where the "Application Settings" option is within CART (nested with the "Edit" toolbar heading)](../resources/installation/slicer_settings.png)

4. In the resulting popup, select `Modules` from the left sidebar:

![Screenshot showing the popup resulting from selecting "Application Settings", with the "Modules" option highlighted on the left-hand side.](../resources/installation/slicer_config_init.png)

5. Drag-and-drop the `CART.py` file onto to the "Additional Module Paths" panel
6. Confirm the registration by selecting "OK" on the bottom right:

![Screenshot showing the modules panel within Slicer's "Application Settings", with a large "Restart required!" noticed along the bottom. The "Ok" button is highlighted.](../resources/installation/slicer_config_confirm.png)

7. Restart Slicer (it should prompt you to do so immediately).

CART should now appear as one of the modules available to Slicer, under the "Utilities" section:

![Screenshot showing the modules dropdown within Slicer, with the "Utilities" nested menu open. The CART entry is highlighted, with its logo (a small shopping cart filled with various office supplies)](../resources/installation/slicer_cart_path.png)
