import sys, random
import Items
from stdlib import Map, Array, List, Random

class Randomizer(object):
    # seed : rand seed
    # difficultyTarget : max diff
    # locations : items locations
    # qty : dictionary telling how many tanks and ammo will be distributed. keys are:
    #       'missile', 'super', 'powerBomb' : relative weight of ammo distribution (ex:3/3/1)
    #       'energy' : can be 'sparse' (5 tanks), 'medium' (11 tanks), 'vanilla' (14 Etanks, 4 reserves)
    #       'minors' : percentage of ammo to distribute. 100 being vanilla
    # sampleSize : possible items sample size between 1 and 100. Has to be > 1 for choose dict to be relevant.
    # choose : relative weight dicts for choosing items (key 'Items') and locations (key 'Locations').
    #          Weights gives the probability a method will be used to choose next item or location.
    #          Item dict : 'Random' => choose next item randomly
    #                      'MinProgression' => between possible items, choose the one that opens up
    #                                          the least amount of new locations (slow/hard)
    #                      'MaxProgression' => between possible items, choose the one that opens up
    #                                          the most amount of new locations (fast/easy)
    #          Locations dict : 'Random' => choose next location randomly
    #                           'MinDiff' => between possible locations, choose the one with the lowest
    #                                        access difficulty
    #                           'MaxDiff' => between possible locations, choose the one with the highest
    #                                        access difficulty
    #                           'SpreadProgression' => if item to place is a progression item, will try
    #                                                  to put it as far away as possible from already
    #                                                  placed progression items.
    #                                                  if not, this is equivalent to Random
    # restrictions : item placement restrictions dict. values are booleans. keys :
    #                'Suits' : no suits early game
    #                'SpeedScrew' : no speed or screw in the very first rooms
    #                'MajorMinor' : if true, will put major items in major locations, and minor items
    #                               in minor locations
    def __init__(self, seed, difficultyTarget, locations, qty, sampleSize, choose, restrictions):
        random.seed(seed)

        # we assume that 'choose' dict is perfectly formed, that is all keys
        # below are defined in the appropriate weight dicts
        self.chooseItemRanges = self.getRangeDict(choose['Items'])
        self.chooseItemFuncs = {
            'Random' : self.chooseItemRandom,
            'MinProgression' : self.chooseItemMinProgression,
            'MaxProgression' : self.chooseItemMaxProgression
        }
        self.chooseLocRanges = self.getRangeDict(choose['Locations'])
        self.chooseLocFuncs = {
            'Random' : self.chooseLocationRandom,
            'MinDiff' : self.chooseLocationMinDiff,
            'MaxDiff' : self.chooseLocationMaxDiff,
            'SpreadProgression' : self.chooseLocationSpreadProgression
        }
        self.restrictions = restrictions
        self.itemPool = Items.getItemPool(qty)
        self.difficultyTarget = difficultyTarget
        self.locationPool = locations
        self.sampleSize = sampleSize
        
        # list of locations not already used
        self.unusedLocations = locations
        # list of locations already used
        self.usedLocations = []
        self.progressionLocs = []

    def locAvailable(self, loc, items):
        result = loc["Available"](items)
        return result.bool is True and result.difficulty <= self.difficultyTarget

    def locPostAvailable(self, loc, items):
        if not 'PostAvailable' in loc:
            return True
        result = loc["PostAvailable"](items)
#        print("POST " + str(result.bool))
        return result.bool is True and result.difficulty <= self.difficultyTarget

    def currentLocations(self, items):
        # loop on all the location pool and check if the loc is not already used and if the available function is true
        # 
        # items: list of items, each item is a dict
        # itemLocations: list of dict with the current association of (item - location)
        # locationPool: list of the 100 locations
        #
        # return: list of locations

        # keep only the item type, it's too slow otherwise
        items = [item["Type"] for item in items]
        avail = lambda loc: self.locAvailable(loc, items)
        
        return List.filter(avail, self.unusedLocations)

    def canPlaceItem(self, item, itemLocations):
        # for an item check if a least one location can accept it, without checking
        # the available functions
        #
        # item: dict of an item
        # itemLocations: list of locations
        #
        # return bool
        return List.exists(lambda loc: self.canPlaceAtLocation(item, loc), itemLocations)

    def possibleItems(self, curLocs, items, itemLocations, itemPool, locationPool):
        # loop on all the items in the item pool of not already place items and return those that can be 
        #
        # items: list of items already placed
        # itemLocations: list of dict with the current association of (item - location)
        # itemPool: list of the items not already placed
        # locationPool: list of the 100 locations
        #
        # return list of items eligible for next placement
        result = []
        random.shuffle(itemPool)
        for item in itemPool:
            if self.checkItem(curLocs, item, items, itemLocations, locationPool):
                result.append(item)
                if len(result) >= self.sampleSize:
                    break
        return result

    def removeItem(self, itemType, itemPool):
        # recursive loop on the item pool to remove the first occurence of the item
        #
        # itemType: the name of the item to remove
        # itemPool: the items not already placed
        #
        # return the itemPool without one itemType
        i=0
        for item in itemPool:
            if item['Type'] == itemType:
                return itemPool[0:i] + itemPool[i+1:]
            i+=1

        return itemPool

    # from a relative weight dictionary, gives a normalized range dictionary
    # example :
    # { 'a' : 10, 'b' : 17, 'c' : 3 } => {'c': 0.1, 'a':0.4333333, 'b':1 }
    def getRangeDict(self, weightDict):
        total = float(sum(weightDict.values()))
        rangeDict = {}
        current = 0.0
        for k in sorted(weightDict, key=weightDict.get):
            w = float(weightDict[k]) / total
            current += w
            rangeDict[k] = current
        # print(weightDict)
        # print(rangeDict)
            
        return rangeDict

    def getChooseFunc(self, rangeDict, funcDict):
        r = random.random()
        for v in sorted(rangeDict, key=rangeDict.get):
            f = funcDict[v]
            if r < rangeDict[v]:
                return f
        return f
    
    def chooseItemRandom(self, items):
        return items[random.randint(0, len(items)-1)]

    def chooseItemMinProgression(self, items):
        minNewLocs = 1000
        ret = None
        
        for item in items:
            if item in self.failItems:
                continue
            newLocs = len(self.currentLocations(self.currentItems + [item]))
            if newLocs < minNewLocs:
                minNewLocs = newLocs
                ret = item
        return ret

    def chooseItemMaxProgression(self, items):
        maxNewLocs = 0
        ret = None
        
        for item in items:
            if item in self.failItems:
                continue
            newLocs = len(self.currentLocations(self.currentItems + [item]))
            if newLocs > maxNewLocs:
                maxNewLocs = newLocs
                ret = item
        return ret    

    def chooseItem(self, items):
        random.shuffle(items)
        return self.getChooseFunc(self.chooseItemRanges, self.chooseItemFuncs)(items)
        
    def chooseLocationRandom(self, availableLocations, item):
        return availableLocations[random.randint(0, len(availableLocations)-1)]

    def chooseLocationMaxDiff(self, availableLocations, item):
        return max(availableLocations, key=lambda loc:loc['Available'](self.currentItems).difficulty)

    def chooseLocationMinDiff(self, availableLocations, item):
        return min(availableLocations, key=lambda loc:loc['Available'](self.currentItems).difficulty)

    # gives a general "distance" of a particular location compared to other locations
    def areaDistance(self, loc, otherLocs):
        areas = [l['Area'] for l in otherLocs]
        cnt = areas.count(loc['Area'])
        d = None
        if cnt == 0:
            d = 2
        else:
            d = 1.0/cnt
        return d
    
    def chooseLocationSpreadProgression(self, availableLocations, item):
        if item['Category'] == 'Progression':
            return max(availableLocations, key=lambda loc:self.areaDistance(loc, self.progressionLocs))
        else:
            return self.chooseLocationRandom(availableLocations, item)

    def chooseLocation(self, availableLocations, item):
        random.shuffle(availableLocations)
        return self.getChooseFunc(self.chooseLocRanges, self.chooseLocFuncs)(availableLocations, item)
    
    def getItemToPlace(self, items, itemPool):        
        itemsLen = len(items)
        if itemsLen == 0:
            item = List.item(random.randint(0, len(itemPool)-1), itemPool)
        else:
            item = self.chooseItem(items)
        return item

    def placeItem(self, items, itemPool, locations):
        # 
        #
        # items: possible items to place
        # itemPool: 
        # locations: locations available
        #
        # returns a dict with the item and the location
        item = self.getItemToPlace(items, itemPool)
        currentItems = [i["Type"] for i in self.currentItems]
        currentItems.append(item['Type'])
        availableLocations = List.filter(lambda loc: self.canPlaceAtLocation(item, loc) and self.locPostAvailable(loc, currentItems), locations)
        if len(availableLocations) == 0:
            self.failItems.append(item)
            return None
        location = self.chooseLocation(availableLocations, item)
        if item['Category'] == 'Progression':
            self.progressionLocs.append(location)
        
        self.usedLocations += [location]
        i=0
        for loc in self.unusedLocations:
            if loc == location:
                self.unusedLocations = self.unusedLocations[0:i] + self.unusedLocations[i+1:]
            i+=1

        if 'Pickup' in location:
            location['Pickup']()
            
        return {'Item': item, 'Location': location}

    def checkItem(self, curLocs, item, items, itemLocations, locationPool):
        # get the list of unused locations accessible with the given items (old),
        # the list of unused locations accessible with the given items and the new item (new).
        # check that there's a major location in the new list for next iteration of placement.
        # check that there's more 
        #
        # item: dict of the item to check
        # items: list of items already placed
        # itemLocations: list of dict with the current association of (item - location)
        # locationPool: list of the 100 locations
        #
        # return bool
        oldLocations = curLocs
        canPlaceIt = self.canPlaceItem(item, oldLocations)
        if canPlaceIt is False:
            return False

        newLocations = self.currentLocations([item] + items)
        newLocationsHasMajor = List.exists(lambda l: l["Class"] == 'Major', newLocations)

        return newLocationsHasMajor and len(newLocations) > len(oldLocations)
    
    def canPlaceAtLocation(self, item, location):
        # check item class and location class, then for special items restrict some locations/areas
        #
        # item: dict of an item
        # location: dict of a location
        if self.restrictions['MajorMinor'] is True:        
            matchingClass = (location["Class"] == item["Class"])
            if matchingClass is False:
                return False

        if self.restrictions['Suits'] is True:
            if item["Type"] == "Gravity":
                return ((not (location["Area"] == "Crateria" or location["Area"] == "Brinstar"))
                        or location["Name"] == "X-Ray Scope" or location["Name"] == "Energy Tank, Waterway")
            elif item["Type"] == "Varia":
                return (not (location["Area"] == "Crateria"
                             or location["Name"] == "Morphing Ball"
                             or location["Name"] == "Missile (blue Brinstar middle)"
                             or location["Name"] == "Energy Tank, Brinstar Ceiling"))
        if self.restrictions['SpeedScrew'] is True and (item["Type"] == "SpeedBooster" or item["Type"] == "ScrewAttack"):
            return (not (location["Name"] == "Morphing Ball"
                         or location["Name"] == "Missile (blue Brinstar middle)"
                         or location["Name"] == "Energy Tank, Brinstar Ceiling"))

        return True

    def generateItems(self):
        items = []
        itemLocations = []
        self.currentItems = items
        while len(self.itemPool) > 0:
            curLocs = self.currentLocations(items)
            itemLocation = None
            self.failItems = []
            while itemLocation is None:
                posItems = self.possibleItems(curLocs, items, itemLocations, self.itemPool, self.locationPool)
#                print(str(len(posItems)) + " possible items")
                itemLocation = self.placeItem(posItems, self.itemPool, curLocs)
                if len(self.failItems) >= len(posItems):
                    break
            if itemLocation is None:
                return None
#            print(str(len(self.currentItems) + 1) + ':' + itemLocation['Item']['Type'] + ' at ' + itemLocation['Location']['Name'])
            sys.stdout.write('.')
            sys.stdout.flush()
            items.append(itemLocation['Item'])
            itemLocations.append(itemLocation)
            self.itemPool = self.removeItem(itemLocation['Item']['Type'], self.itemPool)
        print("")
            
        return itemLocations
